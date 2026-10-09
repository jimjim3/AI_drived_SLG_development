"""Random agent for sanity checks and reproducibility tests."""

from __future__ import annotations

import random

from ..schema import AgentDecision, GameState, LegalAction, OfficerState
from .base import Agent


class RandomAgent(Agent):
    name = "random"

    def __init__(self, rng: random.Random):
        self.rng = rng

    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        la = self.rng.choice(legal)
        params: dict[str, object] = {}
        for pname, ps in la.params.items():
            if ps.is_discrete():
                params[pname] = self.rng.choice(list(ps.choices))
            elif ps.step is not None:
                steps = int((ps.max - ps.min) // ps.step)
                params[pname] = ps.min + self.rng.randint(0, steps) * ps.step
            else:
                params[pname] = self.rng.uniform(ps.min, ps.max)
        return AgentDecision(officer.officer_id, la.action, params, "random")
