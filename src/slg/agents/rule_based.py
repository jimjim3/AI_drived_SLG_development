"""Deterministic rule-based agent with a selectable play style.

Priority (per officer, in order):
  a. food is tight and develop_agri is legal -> develop_agri
  b. strong enough officer and siege is legal: siege the weakest adjacent
     enemy city when 70% of the garrison clears the style's ratio
  c. politics >= war: develop the lowest of agriculture/commerce/defense
  d. war > politics: recruit while below 2.5x agriculture
  e. any legal develop_*, finally rest
"""

from __future__ import annotations

from ..schema import AgentDecision, GameState, LegalAction, OfficerState
from .base import Agent


class RuleBasedAgent(Agent):
    name = "rule_based"
    STYLES = ("balanced", "aggressive", "turtle")
    SIEGE_RATIO = {"aggressive": 1.0, "balanced": 1.4, "turtle": 2.0}
    SIEGE_MIN_COMBAT = 70        # (war + leadership) / 2 threshold to attack
    SIEGE_TROOP_FRACTION = 0.7   # share of the garrison sent on a siege
    RECRUIT_FOOD_MULT = 2.5      # recruit while troops < 2.5 * agriculture
    RECRUIT_TARGET = 600         # preferred recruit size

    def __init__(self, style: str = "balanced"):
        if style not in self.SIEGE_RATIO:
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

        # b. Attack the weakest adjacent enemy city when the odds look right.
        siege = by_action.get("siege")
        if (
            siege is not None
            and (officer.war + officer.leadership) / 2 >= self.SIEGE_MIN_COMBAT
        ):
            targets = [state.city(tid) for tid in siege.params["to"].choices]
            weakest = min(targets, key=lambda t: (t.troops, t.city_id))
            ratio = self.SIEGE_RATIO[self.style]
            if city.troops * self.SIEGE_TROOP_FRACTION >= weakest.troops * ratio:
                spec = siege.params["troops"]
                troops = int(city.troops * self.SIEGE_TROOP_FRACTION) // 100 * 100
                troops = min(spec.max, max(spec.min, troops))
                return AgentDecision(
                    officer.officer_id,
                    "siege",
                    {"to": weakest.city_id, "troops": troops},
                    "siege weakest",
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
