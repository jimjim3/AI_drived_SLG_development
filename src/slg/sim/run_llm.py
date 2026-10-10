"""CLI entry point for running SLG simulation with LLM / Demo backends."""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys

from ..agents.backends import CommandCompleter, DemoCompleter, OpenAIChatCompleter
from ..agents.llm_agent import Completer, LLMFactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..engine.game import Game, compute_winner
from ..engine.initial_state import build_initial_state
from ..schema import TurnLog


def build_completer(args: argparse.Namespace) -> Completer | None:
    """Build a Completer instance from parsed CLI arguments.

    Returns None if no backend options are specified.
    """
    has_command = getattr(args, "command", None) is not None and len(args.command) > 0
    has_openai = bool(getattr(args, "openai_base_url", None) and getattr(args, "model", None))
    has_demo = bool(getattr(args, "demo", False))

    if not (has_demo or has_command or has_openai):
        return None

    if has_demo:
        return DemoCompleter()
    elif has_command:
        return CommandCompleter(args.command)
    else:
        return OpenAIChatCompleter(
            base_url=args.openai_base_url,
            model=args.model,
            api_key_env=args.api_key_env,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run SLG simulation with LLM / Demo backends.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--turns", type=int, default=10, help="Number of turns (default: 10)")
    parser.add_argument(
        "--llm-faction",
        action="append",
        default=None,
        help="Faction ID(s) controlled by LLM (default: faction_2, can specify multiple)",
    )
    parser.add_argument("--demo", action="store_true", help="Use DemoCompleter backend")
    parser.add_argument("--openai-base-url", type=str, default=None, help="OpenAI-compatible base URL")
    parser.add_argument("--model", type=str, default=None, help="OpenAI model name")
    parser.add_argument("--api-key-env", type=str, default=None, help="Env var name for API key")
    parser.add_argument("--save-log", type=str, default=None, help="Path to save TurnLog JSON")
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=None,
        help="Subprocess command for CommandCompleter",
    )

    args = parser.parse_args(argv)

    completer = build_completer(args)
    if completer is None:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    llm_factions = set(args.llm_faction if args.llm_faction is not None else ["faction_2"])

    state = build_initial_state()
    rng = random.Random(args.seed)

    agents_by_faction = {}
    for fid in sorted(state.factions):
        if fid in llm_factions:
            agents_by_faction[fid] = LLMFactionAgent(completer)
        else:
            agents_by_faction[fid] = RuleBasedAgent("balanced")

    game = Game(state, agents_by_faction, rng)

    for _ in range(args.turns):
        active = sum(1 for f in game.state.factions.values() if f.is_active)
        if active <= 1:
            break
        game.step()
        curr_turn = game.state.turn
        for flog in game.faction_logs:
            if flog.turn == curr_turn and flog.faction_id in llm_factions:
                if flog.chronicle:
                    print(f"[{flog.faction_id} T{curr_turn}] {flog.chronicle}")
                if flog.rejected:
                    print(f"[{flog.faction_id} T{curr_turn}] rejected: {flog.rejected}")

    winner = compute_winner(game.state)
    print(f"winner: {winner}")
    print(f"stats: {game.stats}")

    for fid in sorted(llm_factions):
        agent = agents_by_faction.get(fid)
        if agent is not None and hasattr(agent, "usage"):
            usage = dict(agent.usage)
            est_tokens = (usage.get("prompt_chars", 0) + usage.get("response_chars", 0)) // 2
            print(f"[{fid}] usage: {usage}, estimated tokens: {est_tokens}")

    if args.save_log:
        log = TurnLog(
            seed=args.seed,
            turns=args.turns,
            entries=tuple(game.log_entries),
            stats=tuple(sorted(game.stats.items())),
            faction_logs=tuple(game.faction_logs),
        )
        with open(args.save_log, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(log), f, default=str, ensure_ascii=False)

    sys.exit(0)


if __name__ == "__main__":
    main()
