"""Deterministic rule-based agent for the M0a skeleton.

Priority:
  1. siege the weakest enemy city when clearly advantaged
  2. recruit up to the legal maximum while below the troop cap
  3. develop agriculture, then commerce, then defense
  4. rest
"""

from __future__ import annotations

from ..schema import AgentDecision, GameState, LegalAction, OfficerState
from .base import Agent


class RuleBasedAgent(Agent):
    name = "rule_based"
    SIEGE_TROOP_THRESHOLD = 1500
    SIEGE_ADVANTAGE = 1.5
    RECRUIT_TROOP_CAP = 3000

    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        city = state.city(officer.city_id)
        by_action = {la.action: la for la in legal}

        siege = by_action.get("siege")
        if siege is not None and city.troops >= self.SIEGE_TROOP_THRESHOLD:
            target_ids = list(siege.params["to"].choices)
            candidates = [
                state.city(tid)
                for tid in target_ids
                if city.troops > state.city(tid).troops * self.SIEGE_ADVANTAGE
            ]
            if candidates:
                target = min(candidates, key=lambda c: (c.troops, c.city_id))
                return AgentDecision(
                    officer.officer_id,
                    "siege",
                    {"to": target.city_id},
                    "siege weakest",
                )

        recruit = by_action.get("recruit")
        if recruit is not None and city.troops < self.RECRUIT_TROOP_CAP:
            troops = int(recruit.params["troops"].max)
            return AgentDecision(
                officer.officer_id,
                "recruit",
                {"troops": troops},
                "build army",
            )

        for action in ("develop_agri", "develop_commerce", "develop_defense"):
            if action in by_action:
                return AgentDecision(officer.officer_id, action, {}, "develop")

        return AgentDecision(officer.officer_id, "rest", {}, "rest")
