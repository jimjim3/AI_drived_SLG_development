"""Deterministic replay: re-run a game from a TurnLog and reproduce the result."""

from __future__ import annotations

import random
from typing import ClassVar, Sequence

from ..agents.base import Agent, AgentError, FactionAgent
from ..engine.game import Game, compute_winner
from ..engine.initial_state import build_initial_state
from ..schema import (
    AgentDecision,
    FactionPlan,
    FactionTurnLog,
    GameState,
    LegalAction,
    OfficerState,
    TurnLog,
)
from .headless import GameResult


class ReplayFactionAgent(FactionAgent):
    name: ClassVar[str] = "replay"

    def __init__(self, faction_logs: Sequence[FactionTurnLog]) -> None:
        self._records: dict[tuple[int, str], tuple[AgentDecision, ...]] = {}
        self._faction_level_factions: set[str] = set()
        for log in faction_logs:
            if log.ordered or log.delegated:
                self._faction_level_factions.add(log.faction_id)
            if log.ordered:
                dec_by_oid = {dec.officer_id: dec for dec in log.executed}
                self._records[(log.turn, log.faction_id)] = tuple(
                    dec_by_oid[oid] for oid in log.ordered if oid in dec_by_oid
                )
            elif log.delegated:
                self._records[(log.turn, log.faction_id)] = ()
            else:
                self._records[(log.turn, log.faction_id)] = log.executed

    def is_faction_level(self, faction_id: str) -> bool:
        return faction_id in self._faction_level_factions

    def decide(self, view) -> FactionPlan:
        key = (view.turn, view.faction_id)
        if key not in self._records:
            raise AgentError(f"No replay log for turn {view.turn}, faction {view.faction_id}")
        return FactionPlan(orders=self._records[key])


class ReplayDelegateAgent(Agent):
    name: ClassVar[str] = "replay_delegate"

    def __init__(self, faction_logs: Sequence[FactionTurnLog]) -> None:
        self._records: dict[tuple[int, str], AgentDecision] = {}
        for log in faction_logs:
            for decision in log.executed:
                self._records[(log.turn, decision.officer_id)] = decision

    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        key = (state.turn, officer.officer_id)
        if key not in self._records:
            raise AgentError(f"No replay log for turn {state.turn}, officer {officer.officer_id}")
        return self._records[key]


# Backward compatibility alias
ReplayAgent = ReplayFactionAgent


def replay(log: TurnLog) -> GameResult:
    scenario = getattr(log, "scenario", "default")
    state = build_initial_state(scenario=scenario)
    rng = random.Random(log.seed)

    factions_in_log = sorted(set(fl.faction_id for fl in log.faction_logs))
    agents_by_faction = {
        fid: ReplayFactionAgent(log.faction_logs)
        for fid in factions_in_log
    }
    delegate_agent = ReplayDelegateAgent(log.faction_logs)

    game = Game(state, agents_by_faction, rng, delegate_agent=delegate_agent)
    final_state = game.run(log.turns)

    return GameResult(
        final_state=final_state,
        stats=dict(game.stats),
        events=tuple(game.events),
        winner=compute_winner(final_state),
        log=log,
        incidents=tuple(game.incidents),
    )
