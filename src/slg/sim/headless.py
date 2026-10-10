"""Headless simulation entry point for M0a."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Mapping

from ..agents.base import Agent, FactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..engine.game import Game, compute_winner
from ..engine.initial_state import build_initial_state
from ..schema import GameState, ResolutionEvent, TurnLog


@dataclass(frozen=True)
class GameResult:
    final_state: GameState
    stats: Mapping[str, int]
    events: tuple[ResolutionEvent, ...]
    winner: str | None
    log: TurnLog | None = None
    usage: Mapping[str, dict] = field(default_factory=dict)
    incidents: tuple = ()


def run_headless(
    seed: int = 42,
    turns: int = 20,
    agents_by_faction: Mapping[str, Agent | FactionAgent] | None = None,
) -> GameResult:
    """Run a complete headless game and return its result.

    When ``agents_by_faction`` is omitted, the rule-based agent is used with a
    different style per faction (faction ids sorted): faction_1 "balanced",
    faction_2 "balanced", faction_3 "balanced". A single seeded RNG is shared
    by the engine and any stochastic resolution, so the same seed reproduces
    the same result.
    """
    rng = random.Random(seed)
    state = build_initial_state()
    if agents_by_faction is None:
        default_styles = ("balanced", "balanced", "balanced")
        agents_by_faction = {
            fid: RuleBasedAgent(default_styles[i])
            for i, fid in enumerate(sorted(state.factions))
        }

    game = Game(state, agents_by_faction, rng)
    final_state = game.run(turns)
    log = TurnLog(
        seed=seed,
        turns=turns,
        entries=tuple(game.log_entries),
        stats=tuple(sorted(game.stats.items())),
        faction_logs=tuple(game.faction_logs),
    )
    usage = {
        fid: dict(agent.usage)
        for fid, agent in agents_by_faction.items()
        if hasattr(agent, "usage")
    }
    return GameResult(
        final_state=final_state,
        stats=dict(game.stats),
        events=tuple(game.events),
        winner=compute_winner(final_state),
        log=log,
        usage=usage,
        incidents=tuple(game.incidents),
    )
