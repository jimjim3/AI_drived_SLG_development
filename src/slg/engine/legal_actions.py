"""Generate the set of legal actions for an officer in the current state.

The engine is the single source of truth: an action is legal only if the
engine's rules allow it right now. Agents may only choose from this list.
"""

from __future__ import annotations

from ..schema import (
    DEVELOP_COST,
    GOLD_PER_TROOP,
    MAX_RECRUIT,
    MIN_RECRUIT,
    MIN_SIEGE_TROOPS,
    RECRUIT_STEP,
    GameState,
    LegalAction,
    OfficerState,
    ParamSpec,
)


def generate_legal_actions(state: GameState, officer: OfficerState) -> list[LegalAction]:
    city = state.city(officer.city_id)
    actions: list[LegalAction] = []

    if city.gold >= DEVELOP_COST:
        actions.append(LegalAction("develop_agri", cost=DEVELOP_COST, note="agri +50"))
        actions.append(LegalAction("develop_commerce", cost=DEVELOP_COST, note="commerce +50"))
        actions.append(LegalAction("develop_defense", cost=DEVELOP_COST, note="defense +25"))

    max_troops = min(MAX_RECRUIT, city.gold // GOLD_PER_TROOP)
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
        if c.owner == officer.faction_id and c.city_id != officer.city_id
    )
    if friendly_other:
        actions.append(LegalAction(
            "move",
            params={"to": ParamSpec("to", choices=tuple(friendly_other))},
            cost=0,
            note="relocate officer",
        ))

    enemy_cities = sorted(
        c.city_id for c in state.cities.values()
        if c.owner != officer.faction_id
    )
    if city.troops >= MIN_SIEGE_TROOPS and enemy_cities:
        actions.append(LegalAction(
            "siege",
            params={"to": ParamSpec("to", choices=tuple(enemy_cities))},
            cost=0,
            note=f"from {city.troops} troops",
        ))

    actions.append(LegalAction("rest", cost=0, note="always available"))
    return actions
