"""Re-validate agent decisions against the current state.

The engine is the single source of truth: even though the agent was given a
list of legal actions, every decision is re-checked here before resolution.
This is the safety net that makes the AI a replaceable, untrusted plugin.
"""

from __future__ import annotations

from ..schema import (
    DEVELOP_COST,
    GOLD_PER_TROOP,
    AgentDecision,
    GameState,
    OfficerState,
)
from . import combat
from .legal_actions import generate_legal_actions

KNOWN_ACTIONS = {
    "develop_agri", "develop_commerce", "develop_defense",
    "recruit", "move", "siege", "rest",
}


def _action_cost(action: str, params) -> int:
    if action in ("develop_agri", "develop_commerce", "develop_defense"):
        return DEVELOP_COST
    if action == "recruit":
        return int(params.get("troops", 0)) * GOLD_PER_TROOP
    return 0


def validate_decision(state: GameState, officer: OfficerState, decision: AgentDecision) -> tuple[bool, str]:
    if decision.officer_id != officer.officer_id:
        return False, "officer_id mismatch"
    if not officer.is_alive:
        return False, "officer not alive"
    action = decision.action
    if action not in KNOWN_ACTIONS:
        return False, f"unknown action {action!r}"
    city = state.city(officer.city_id)
    legal = {la.action: la for la in generate_legal_actions(state, officer)}
    if action not in legal:
        return False, f"action {action!r} not legal"
    spec = legal[action]
    for pname in spec.params:
        if pname not in decision.params:
            return False, f"missing required param {pname!r}"
    for pname, pvalue in decision.params.items():
        if pname not in spec.params:
            return False, f"unknown param {pname!r}"
        ps = spec.params[pname]
        if ps.is_discrete():
            if pvalue not in ps.choices:
                return False, f"param {pname}={pvalue!r} not in choices"
        else:
            # AI output is untrusted: a non-numeric value (e.g. "600人", None, a list) must be rejected, not crash.
            if isinstance(pvalue, bool) or not isinstance(pvalue, (int, float)) or pvalue != pvalue:
                return False, f"param {pname}={pvalue!r} is not a number"
            if pvalue < ps.min or pvalue > ps.max:
                return False, f"param {pname}={pvalue!r} out of range [{ps.min}, {ps.max}]"
            if ps.step and (pvalue - ps.min) % ps.step != 0:
                return False, f"param {pname}={pvalue!r} not on step {ps.step}"
    if action == "siege":
        need = combat.march_food(officer.city_id, decision.params["to"], int(decision.params["troops"]))
        if city.food < need:
            return False, f"insufficient food for the march: need {need}, have {city.food}"
    cost = _action_cost(action, decision.params)
    if city.gold < cost:
        return False, f"insufficient gold: need {cost}, have {city.gold}"
    return True, "ok"
