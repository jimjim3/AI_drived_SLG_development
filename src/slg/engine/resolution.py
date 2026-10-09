"""Apply validated decisions to game state (copy-on-write).

Every function returns a new :class:`GameState` and a :class:`ResolutionEvent`;
the input state is never mutated.
"""

from __future__ import annotations

import random
from dataclasses import replace

from ..schema import (
    DEVELOP_COST,
    GOLD_PER_TROOP,
    AgentDecision,
    CityState,
    GameState,
    OfficerState,
    ResolutionEvent,
)

DEVELOP_AGRICULTURE_GAIN = 50
DEVELOP_COMMERCE_GAIN = 50
DEVELOP_DEFENSE_GAIN = 25
REPEL_LOSS_NUMERATOR = 3   # 30% loss on a repelled siege
REPEL_LOSS_DENOMINATOR = 10


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
        new_city = replace(city, gold=city.gold - DEVELOP_COST,
                           agriculture=city.agriculture + DEVELOP_AGRICULTURE_GAIN)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"agri +{DEVELOP_AGRICULTURE_GAIN}")
        return _replace_city(state, new_city), event

    if action == "develop_commerce":
        new_city = replace(city, gold=city.gold - DEVELOP_COST,
                           commerce=city.commerce + DEVELOP_COMMERCE_GAIN)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"commerce +{DEVELOP_COMMERCE_GAIN}")
        return _replace_city(state, new_city), event

    if action == "develop_defense":
        new_city = replace(city, gold=city.gold - DEVELOP_COST,
                           defense=city.defense + DEVELOP_DEFENSE_GAIN)
        event = ResolutionEvent(state.turn, officer.officer_id, officer.faction_id,
                                action, city.city_id, f"defense +{DEVELOP_DEFENSE_GAIN}")
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


def _resolve_siege(
    state: GameState,
    officer: OfficerState,
    decision: AgentDecision,
    rng: random.Random,
) -> tuple[GameState, ResolutionEvent]:
    target_id = decision.params["to"]
    attacker_city = state.city(officer.city_id)
    defender_city = state.city(target_id)
    attacker_faction = officer.faction_id
    defender_faction = defender_city.owner

    attack = attacker_city.troops * (officer.leadership / 100) * rng.uniform(0.8, 1.2)
    defense = defender_city.troops * (1.0 + defender_city.defense / 100) * rng.uniform(0.8, 1.2)

    cities = dict(state.cities)
    officers = dict(state.officers)

    if attack > defense:
        # Capture: city changes owner, both garrisons are consumed.
        cities[target_id] = replace(defender_city, owner=attacker_faction, troops=0)
        cities[officer.city_id] = replace(attacker_city, troops=0)

        captured_officers = []
        old_owner_cities = sorted(
            c.city_id for c in state.cities.values()
            if c.owner == defender_faction and c.city_id != target_id
        )
        for o in state.officers.values():
            if o.city_id == target_id and o.faction_id == defender_faction and o.is_alive:
                if old_owner_cities:
                    officers[o.officer_id] = replace(o, city_id=old_owner_cities[0])
                else:
                    officers[o.officer_id] = replace(o, is_alive=False)
                    captured_officers.append(o.officer_id)

        new_state = replace(state, cities=cities, officers=officers)
        event = ResolutionEvent(
            state.turn, officer.officer_id, attacker_faction, "siege", target_id,
            f"captured {defender_city.name} (atk {attack:.0f} > def {defense:.0f})",
            captured_city=target_id,
            captured_officers=tuple(captured_officers),
        )
        return new_state, event

    # Repel: both sides lose 30% of their troops; the officer stays put.
    attacker_loss = attacker_city.troops * REPEL_LOSS_NUMERATOR // REPEL_LOSS_DENOMINATOR
    defender_loss = defender_city.troops * REPEL_LOSS_NUMERATOR // REPEL_LOSS_DENOMINATOR
    cities[officer.city_id] = replace(attacker_city, troops=attacker_city.troops - attacker_loss)
    cities[target_id] = replace(defender_city, troops=defender_city.troops - defender_loss)
    new_state = replace(state, cities=cities)
    event = ResolutionEvent(
        state.turn, officer.officer_id, attacker_faction, "siege", target_id,
        f"repelled at {defender_city.name} (atk {attack:.0f} <= def {defense:.0f})",
    )
    return new_state, event
