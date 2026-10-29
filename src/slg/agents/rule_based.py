"""Deterministic rule-based agent with a selectable play style.

Priority (per officer, in order):
  a. food is tight and develop_agri is legal -> develop_agri
  b. strong enough officer and siege is legal: siege the adjacent enemy city
     with the best engine-estimated odds when they clear the style's ratio
  c. politics >= war: develop the lowest of agriculture/commerce/defense
  d. war > politics: recruit while below 2.5x agriculture
  e. any legal develop_*, finally rest
"""

from __future__ import annotations

from ..engine import combat
from ..engine.resolution import estimate_siege_ratio
from ..schema import AgentDecision, GameState, LegalAction, OfficerState
from .base import Agent


class RuleBasedAgent(Agent):
    name = "rule_based"
    STYLES = ("balanced", "aggressive", "turtle")
    SIEGE_ODDS = {"aggressive": 1.1, "balanced": 1.3, "turtle": 1.8}  # engine siege-odds ratio to attack
    SIEGE_RATIO = SIEGE_ODDS  # kept for callers that validate the style
    SIEGE_MIN_COMBAT = 70        # (war + leadership) / 2 threshold to attack
    SIEGE_TROOP_FRACTION = 0.7   # share of the garrison sent on a siege
    RECRUIT_FOOD_MULT = 2.5      # recruit while troops < 2.5 * agriculture
    RECRUIT_TARGET = 600         # preferred recruit size

    def __init__(self, style: str = "balanced"):
        if style not in self.SIEGE_ODDS:
            raise ValueError(
                f"unknown style {style!r}; expected one of {self.STYLES}"
            )
        self.style = style

    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        city = state.city(officer.city_id)
        by_action = {la.action: la for la in legal}

        # a. Food is tight: invest in agriculture whenever we can afford it.
        if city.food < city.troops // 10 * 3 and "develop_agri" in by_action:
            return AgentDecision(officer.officer_id, "develop_agri", {}, "fix food")

        # b. Attack the target with the best engine-estimated odds when they clear the style's bar.
        siege = by_action.get("siege")
        if (
            siege is not None
            and (officer.war + officer.leadership) / 2 >= self.SIEGE_MIN_COMBAT
        ):
            spec = siege.params["troops"]
            step = int(spec.step or 100)
            troops = max(int(spec.min), int(spec.max * self.SIEGE_TROOP_FRACTION) // step * step)
            troops = min(int(spec.max), troops)
            best = max(
                ((estimate_siege_ratio(state, officer, tid, troops), tid)
                 for tid in siege.params["to"].choices
                 if combat.march_food(city.city_id, tid, troops) <= city.food),
                key=lambda rt: (rt[0], rt[1]),
                default=None,
            )
            if best is not None and best[0] >= self.SIEGE_ODDS[self.style]:
                return AgentDecision(
                    officer.officer_id,
                    "siege",
                    {"to": best[1], "troops": troops},
                    "siege best odds",
                )

        # c. Politician: develop the weakest economic stat.
        if officer.politics >= officer.war:
            lowest = min(city.agriculture, city.commerce, city.defense)
            for action, value in (
                ("develop_agri", city.agriculture),
                ("develop_commerce", city.commerce),
                ("develop_defense", city.defense),
            ):
                if value == lowest and action in by_action:
                    return AgentDecision(officer.officer_id, action, {}, "develop lowest")

        # d. Warrior: build up the garrison while food can support it.
        recruit = by_action.get("recruit")
        if (
            recruit is not None
            and city.troops < self.RECRUIT_FOOD_MULT * city.agriculture
        ):
            spec = recruit.params["troops"]
            troops = min(spec.max, self.RECRUIT_TARGET)
            troops = max(spec.min, (troops // 100) * 100)
            return AgentDecision(
                officer.officer_id, "recruit", {"troops": troops}, "build army"
            )

        # e. Fallback: any development, then rest.
        for action in ("develop_agri", "develop_commerce", "develop_defense"):
            if action in by_action:
                return AgentDecision(officer.officer_id, action, {}, "develop")

        return AgentDecision(officer.officer_id, "rest", {}, "rest")
