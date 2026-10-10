"""Deterministic replay: re-run a game from a TurnLog and reproduce the result."""

from __future__ import annotations

import random
from typing import ClassVar, Sequence

from ..agents.base import AgentError, FactionAgent
from ..engine.game import Game, compute_winner
from ..engine.initial_state import build_initial_state
from ..schema import (
    FactionPlan,
    FactionTurnLog,
    TurnLog,
)
from .headless import GameResult


class ReplayFactionAgent(FactionAgent):
    name: ClassVar[str] = "replay"

    def __init__(self, faction_logs: Sequence[FactionTurnLog]) -> None:
        self._records = {
            (log.turn, log.faction_id): log.executed
            for log in faction_logs
        }

    def decide(self, view) -> FactionPlan:
        key = (view.turn, view.faction_id)
        if key not in self._records:
            raise AgentError(f"No replay log for turn {view.turn}, faction {view.faction_id}")
        return FactionPlan(orders=self._records[key])


# Backward compatibility alias
ReplayAgent = ReplayFactionAgent


def replay(log: TurnLog) -> GameResult:
    state = build_initial_state()
    rng = random.Random(log.seed)

    factions_in_log = sorted(set(fl.faction_id for fl in log.faction_logs))
    agents_by_faction = {
        fid: ReplayFactionAgent(log.faction_logs)
        for fid in factions_in_log
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
