"""Generate the set of legal actions for an officer in the current state.

The engine is the single source of truth: an action is legal only if the
engine's rules allow it right now. Agents may only choose from this list.
"""

from __future__ import annotations

from . import combat
from ..schema import (
    DEVELOP_COST,
    DEVELOP_AGRICULTURE_BASE,
    DEVELOP_COMMERCE_BASE,
    DEVELOP_DEFENSE_BASE,
    GOLD_PER_TROOP,
    MAX_RECRUIT,
    MIN_RECRUIT,
    MIN_SIEGE_TROOPS,
    RECRUIT_STEP,
    SIEGE_MIN_GARRISON,
    SIEGE_TROOP_STEP,
    GameState,
    LegalAction,
    OfficerState,
    ParamSpec,
    develop_gain,
)


def generate_legal_actions(state: GameState, officer: OfficerState) -> list[LegalAction]:
    city = state.city(officer.city_id)
    actions: list[LegalAction] = []

    agri_cap, commerce_cap, troop_cap = combat.city_caps(city.city_id)
    if city.gold >= DEVELOP_COST:
        agri_gain = develop_gain(DEVELOP_AGRICULTURE_BASE, officer.politics)
        commerce_gain = develop_gain(DEVELOP_COMMERCE_BASE, officer.politics)
        defense_gain = develop_gain(DEVELOP_DEFENSE_BASE, officer.politics)
        if city.agriculture < agri_cap:
            actions.append(LegalAction("develop_agri", cost=DEVELOP_COST,
                                       note=f"agri +{agri_gain}"))
        if city.commerce < commerce_cap:
            actions.append(LegalAction("develop_commerce", cost=DEVELOP_COST,
                                       note=f"commerce +{commerce_gain}"))
        actions.append(LegalAction("develop_defense", cost=DEVELOP_COST,
                                   note=f"defense +{defense_gain}"))

    max_troops = min(MAX_RECRUIT, city.gold // GOLD_PER_TROOP, max(0, troop_cap - city.troops))
    max_troops = (max_troops // RECRUIT_STEP) * RECRUIT_STEP
    if max_troops >= MIN_RECRUIT:
        actions.append(LegalAction(
            "recruit",
            params={"troops": ParamSpec("troops", min=MIN_RECRUIT, max=max_troops, step=RECRUIT_STEP)},
            cost=MIN_RECRUIT * GOLD_PER_TROOP,
            note=f"max {max_troops}",
        ))

    friendly_other = sorted(
        c.city_id for c in state.cities.values()
        if c.owner == officer.faction_id
        and c.city_id != city.city_id
        and state.adjacent(city.city_id, c.city_id)
    )
    if friendly_other:
        actions.append(LegalAction(
            "move",
            params={"to": ParamSpec("to", choices=tuple(friendly_other))},
            cost=0,
            note="relocate officer to adjacent friendly city",
        ))

    enemy_adjacent = sorted(
        c.city_id for c in state.cities.values()
        if c.owner != officer.faction_id
        and state.adjacent(city.city_id, c.city_id)
    )
    siege_max = (combat.siege_capacity(state, city) // SIEGE_TROOP_STEP) * SIEGE_TROOP_STEP
    if siege_max >= MIN_SIEGE_TROOPS and enemy_adjacent:
        actions.append(LegalAction(
            "siege",
            params={
                "to": ParamSpec("to", choices=tuple(enemy_adjacent)),
                "troops": ParamSpec("troops", min=MIN_SIEGE_TROOPS,
                                    max=siege_max, step=SIEGE_TROOP_STEP),
            },
            cost=0,
            note=(f"from {city.troops} troops, keep {SIEGE_MIN_GARRISON} garrison"
                  + (f"; march food = troops*km/1000, you have {city.food}: "
                     + ", ".join(f"{t}={combat.edge_km(city.city_id, t)}km" for t in enemy_adjacent)
                     if combat.active().march_food_rate > 0 else "")
                  + (", may draw on adjacent friendly cities" if combat.active().pool_factor > 0 else "")),
        ))

    actions.append(LegalAction("rest", cost=0, note="always available"))
    return actions
