"""Apply validated decisions to game state (copy-on-write).

Every function returns a new :class:`GameState` and a :class:`ResolutionEvent`;
the input state is never mutated.
"""

from __future__ import annotations

import random
from dataclasses import replace

from . import combat
from ..schema import (
    DEVELOP_COST,
    DEVELOP_AGRICULTURE_BASE,
    DEVELOP_COMMERCE_BASE,
    DEVELOP_DEFENSE_BASE,
    GOLD_PER_TROOP,
    AgentDecision,
    CityState,
    GameState,
    OfficerState,
    ResolutionEvent,
    develop_gain,
)

# Fallback combat skill for a city with no surviving defending officer.
NO_OFFICER_DEFENSE_SKILL = 40


def _replace_city(state: GameState, city: CityState) -> GameState:
    cities = dict(state.cities)
    cities[city.city_id] = city
    return replace(state, cities=cities)


def _replace_officer(state: GameState, officer: OfficerState) -> GameState:
    officers = dict(state.officers)
    officers[officer.officer_id] = officer
    return replace(state, officers=officers)


def resolve_decision(
    state: GameState,
    officer: OfficerState,
    decision: AgentDecision,
    rng: random.Random,
) -> tuple[GameState, ResolutionEvent]:
    city = state.city(officer.city_id)
    action = decision.action

    if action == "develop_agri":
        gain = develop_gain(DEVELOP_AGRICULTURE_BASE, officer.politics)
        new_city = replace(city, gold=city.gold - DEVELOP_COST,
                           agriculture=city.agriculture + gain)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"agri +{gain}")
        return _replace_city(state, new_city), event

    if action == "develop_commerce":
        gain = develop_gain(DEVELOP_COMMERCE_BASE, officer.politics)
        new_city = replace(city, gold=city.gold - DEVELOP_COST,
                           commerce=city.commerce + gain)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"commerce +{gain}")
        return _replace_city(state, new_city), event

    if action == "develop_defense":
        gain = develop_gain(DEVELOP_DEFENSE_BASE, officer.politics)
        new_city = replace(city, gold=city.gold - DEVELOP_COST,
                           defense=city.defense + gain)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"defense +{gain}")
        return _replace_city(state, new_city), event

    if action == "recruit":
        troops = int(decision.params["troops"])
        cost = troops * GOLD_PER_TROOP
        new_city = replace(city, gold=city.gold - cost, troops=city.troops + troops)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"+{troops} troops (-{cost} gold)")
        return _replace_city(state, new_city), event

    if action == "move":
        dest = decision.params["to"]
        new_officer = replace(officer, city_id=dest)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"moved to {dest}")
        return _replace_officer(state, new_officer), event

    if action == "rest":
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, "rest")
        return state, event

    if action == "siege":
        return _resolve_siege(state, officer, decision, rng)

    raise ValueError(f"unknown action: {action!r}")


def _siege_strengths(
    state: GameState,
    officer: OfficerState,
    target_id: str,
    troops: int,
) -> tuple[float, float]:
    c = int(troops)
    defender_city = state.city(target_id)
    defender_faction = defender_city.owner
    def_troops = defender_city.troops

    atk_base = c * (0.5 + (officer.war + officer.leadership) / 200)
    defenders = [
        o for o in state.officers.values()
        if o.faction_id == defender_faction and o.city_id == target_id and o.is_alive
    ]
    dq = (max((o.war + o.leadership) / 2 for o in defenders)
          if defenders else float(NO_OFFICER_DEFENSE_SKILL))
    rules = combat.active()
    dfn_base = (def_troops * (1 + defender_city.defense / rules.defense_divisor)
                * (rules.dq_base + dq / rules.dq_div))
    return atk_base, dfn_base


def estimate_siege_ratio(
    state: GameState,
    officer: OfficerState,
    target_city_id: str,
    troops: int,
) -> float:
    atk_base, dfn_base = _siege_strengths(state, officer, target_city_id, troops)
    if dfn_base <= 0:
        return float("inf")
    return atk_base / dfn_base


def _resolve_siege(
    state: GameState,
    officer: OfficerState,
    decision: AgentDecision,
    rng: random.Random,
) -> tuple[GameState, ResolutionEvent]:
    target_id = decision.params["to"]
    c = int(decision.params["troops"])
    attacker_city = state.city(officer.city_id)
    defender_city = state.city(target_id)
    attacker_faction = officer.faction_id
    defender_faction = defender_city.owner
    def_troops = defender_city.troops

    atk_base, dfn_base = _siege_strengths(state, officer, target_id, c)

    # Fixed rng draw order: attacker roll first, then defender roll.
    atk = atk_base * rng.uniform(0.85, 1.15)
    dfn = dfn_base * rng.uniform(0.85, 1.15)

    cities = dict(state.cities)
    officers = dict(state.officers)

    if atk > dfn:
        # Victory: survivors garrison the captured city; the origin city keeps
        # only its garrison.
        loss = int(c * min(0.5, max(0.1, 0.4 * dfn / atk)))
        survivors = c - loss
        cities[target_id] = replace(defender_city, owner=attacker_faction, troops=survivors)
        for cid, amount in combat.siege_contributions(state, attacker_city, c):
            cities[cid] = replace(cities[cid], troops=cities[cid].troops - amount)

        captured_officers = []
        fallback_cities = sorted(
            cid for cid, cstate in state.cities.items()
            if cstate.owner == defender_faction and cid != target_id
        )
        for o in state.officers.values():
            if o.faction_id == defender_faction and o.city_id == target_id and o.is_alive:
                if fallback_cities:
                    # Retreat to the faction's other city with the smallest id.
                    officers[o.officer_id] = replace(o, city_id=fallback_cities[0])
                else:
                    # Faction eliminated: the officer is captured and defects.
                    officers[o.officer_id] = replace(
                        o,
                        faction_id=attacker_faction,
                        city_id=target_id,
                        loyalty=min(o.loyalty, 60),
                    )
                    captured_officers.append(o.officer_id)

        officers[officer.officer_id] = replace(officers[officer.officer_id], city_id=target_id)

        new_state = replace(state, cities=cities, officers=officers)
        event = ResolutionEvent(
            state.turn, officer.officer_id, attacker_faction, "siege", target_id,
            f"captured {defender_city.name} (atk {atk:.0f} > def {dfn:.0f}, "
            f"{survivors} troops garrison)",
            captured_city=target_id,
            captured_officers=tuple(captured_officers),
        )
        return new_state, event

    # Repelled: the expedition loses a large share and returns home.
    attacker_loss = int(c * min(0.8, max(0.3, 0.5 * dfn / atk)))
    defender_loss = int(def_troops * min(0.3, 0.15 * atk / dfn))
    parts = combat.siege_contributions(state, attacker_city, c)
    shares = [(cid, attacker_loss * amount // c) for cid, amount in parts]
    shares[0] = (shares[0][0], shares[0][1] + attacker_loss - sum(x for _, x in shares))  # rounding to the origin
    for cid, loss in shares:
        cities[cid] = replace(cities[cid], troops=cities[cid].troops - loss)
    cities[target_id] = replace(defender_city, troops=def_troops - defender_loss)
    new_state = replace(state, cities=cities)
    event = ResolutionEvent(
        state.turn, officer.officer_id, attacker_faction, "siege", target_id,
        f"repelled at {defender_city.name} (atk {atk:.0f} <= def {dfn:.0f}, "
        f"lost {attacker_loss} of {c})",
    )
    return new_state, event
