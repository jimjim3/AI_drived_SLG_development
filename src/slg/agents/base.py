"""Agent interface.

An agent is an untrusted plugin: it receives the current immutable state, one
officer, and the engine-generated legal actions, and returns exactly one
:class:`AgentDecision`. The engine re-validates the decision before applying it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from ..schema import AgentDecision, FactionPlan, GameState, LegalAction, OfficerState

if TYPE_CHECKING:
    from ..engine.view import FactionView


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


class AgentError(Exception):
    """Raised when an agent fails to make a decision."""


class FactionAgent(ABC):
    name: ClassVar[str] = "faction_agent"

    @abstractmethod
    def decide(self, view: FactionView) -> FactionPlan:
        """Return a faction plan for the current turn view."""

