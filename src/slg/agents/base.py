"""Agent interface.

An agent is an untrusted plugin: it receives the current immutable state, one
officer, and the engine-generated legal actions, and returns exactly one
:class:`AgentDecision`. The engine re-validates the decision before applying it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..schema import AgentDecision, GameState, LegalAction, OfficerState


class Agent(ABC):
    name: ClassVar[str] = "agent"

    @abstractmethod
    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        """Return one decision for ``officer`` from ``legal``."""
