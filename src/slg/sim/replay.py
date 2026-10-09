"""Deterministic replay: re-run a game from a TurnLog and reproduce the result."""

from __future__ import annotations

import random
from typing import ClassVar

from ..agents.base import Agent
from ..engine.game import Game
from ..engine.initial_state import build_initial_state
from ..schema import (
    AgentDecision,
    GameState,
    LegalAction,
    LogEntry,
    OfficerState,
    TurnLog,
)
from ..sim.headless import GameResult, compute_winner


class ReplayAgent(Agent):
    name: ClassVar[str] = "replay"

    def __init__(self, entries: tuple[LogEntry, ...]) -> None:
        self._entries = entries
        self._index = 0

    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        entry = self._entries[self._index]
        self._index += 1
        return AgentDecision(
            officer_id=entry.officer_id,
            action=entry.action,
            params=dict(entry.params),
        )


def replay(log: TurnLog) -> GameResult:
    state = build_initial_state()
    rng = random.Random(log.seed)

    entries_by_faction: dict[str, list[LogEntry]] = {}
    for entry in log.entries:
        entries_by_faction.setdefault(entry.faction_id, []).append(entry)

    agents_by_faction = {
        fid: ReplayAgent(tuple(entries))
        for fid, entries in entries_by_faction.items()
    }

    game = Game(state, agents_by_faction, rng)
    final_state = game.run(log.turns)

    return GameResult(
        final_state=final_state,
        stats=dict(game.stats),
        events=tuple(game.events),
        winner=compute_winner(final_state),
        log=log,
    )
