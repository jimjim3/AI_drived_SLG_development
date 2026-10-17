"""CLI entry point for running SLG simulation with LLM / Demo backends."""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys

from ..agents.backends import (
    CircuitBreakerCompleter,
    CommandCompleter,
    DemoCompleter,
    OpenAIChatCompleter,
)
from ..agents.llm_agent import Completer, LLMFactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..engine.game import Game, compute_winner
from ..engine.initial_state import build_initial_state
from ..schema import TurnLog


def _parse_extra_body_json(value: str) -> dict:
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise argparse.ArgumentTypeError(
                f"--extra-body-json must be a JSON object (dict), got {type(parsed).__name__}"
            )
        return parsed
    except Exception as exc:
        if isinstance(exc, argparse.ArgumentTypeError):
            raise
        raise argparse.ArgumentTypeError(f"Invalid JSON for --extra-body-json: {exc}") from exc


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
        base = DemoCompleter()
    elif has_command:
        base = CommandCompleter(args.command)
    else:
        extra_body = getattr(args, "extra_body", None)
        if extra_body is None:
            eb_json = getattr(args, "extra_body_json", None)
            if isinstance(eb_json, str):
                try:
                    extra_body = json.loads(eb_json)
                    if not isinstance(extra_body, dict):
                        raise ValueError(f"--extra-body-json must be a JSON object, got {type(extra_body).__name__}")
                except Exception as exc:
                    raise ValueError(f"Invalid JSON for --extra-body-json: {exc}") from exc
            elif isinstance(eb_json, dict):
                extra_body = eb_json

        base = OpenAIChatCompleter(
            base_url=args.openai_base_url,
            model=args.model,
            api_key_env=args.api_key_env,
            extra_body=extra_body,
            http_retries=getattr(args, "http_retries", 0) or 0,
            min_interval=getattr(args, "min_interval", 0.0) or 0.0,
            **({"timeout": args.http_timeout} if getattr(args, "http_timeout", None) else {}),
        )

    max_errors = getattr(args, "max_consecutive_errors", 3)
    return CircuitBreakerCompleter(base, max_consecutive_errors=max_errors)


def _reorder_command_args(argv: list[str], known_flags: set[str]) -> list[str]:
    if "--command" not in argv:
        return argv
    idx = argv.index("--command")
    before = argv[:idx]
    after = argv[idx + 1 :]
    cmd_tokens = []
    trailing_flags = []
    i = 0
    while i < len(after):
        tok = after[i]
        if tok in known_flags or any(tok.startswith(kf + "=") for kf in known_flags):
            trailing_flags.extend(after[i:])
            break
        cmd_tokens.append(tok)
        i += 1
    return before + trailing_flags + ["--command"] + cmd_tokens


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
    parser.add_argument(
        "--siege-verdict",
        action="store_true",
        help="Show the engine's verdict (不建議/冒險/可行) next to each siege_odds ratio in the LLM prompt",
    )
    parser.add_argument("--openai-base-url", type=str, default=None, help="OpenAI-compatible base URL")
    parser.add_argument("--model", type=str, default=None, help="OpenAI model name")
    parser.add_argument("--api-key-env", type=str, default=None, help="Env var name for API key")
    parser.add_argument(
        "--http-retries",
        type=int,
        default=0,
        help="Extra attempts after HTTP 429/502/503/504, waiting Retry-After or 2,4,8… seconds (default: 0)",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=None,
        help="Read timeout in seconds for each LLM request (default: 120); timeouts are retried when --http-retries > 0",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.0,
        help="Minimum seconds between LLM request starts, for rate-limited endpoints (default: 0)",
    )
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        help="Max consecutive errors before circuit breaker opens (default: 3)",
    )
    parser.add_argument("--save-log", type=str, default=None, help="Path to save TurnLog JSON")
    parser.add_argument("--scenario", type=str, default="default", help="Scenario name (default: default)")
    parser.add_argument(
        "--extra-body-json",
        type=_parse_extra_body_json,
        default=None,
        help="Additional JSON object to merge into OpenAI request body",
    )
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=None,
        help="Subprocess command for CommandCompleter",
    )

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    known = {
        "--seed",
        "--turns",
        "--llm-faction",
        "--demo",
        "--openai-base-url",
        "--model",
        "--api-key-env",
        "--save-log",
        "--max-consecutive-errors",
        "--scenario",
        "--extra-body-json",
    }
    processed_argv = _reorder_command_args(raw_argv, known)
    args = parser.parse_args(processed_argv)

    completer = build_completer(args)
    if completer is None:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    llm_factions = set(args.llm_faction if args.llm_faction is not None else ["faction_2"])

    state = build_initial_state(scenario=args.scenario)
    rng = random.Random(args.seed)

    agents_by_faction = {}
    for fid in sorted(state.factions):
        if fid in llm_factions:
            agents_by_faction[fid] = LLMFactionAgent(completer, siege_verdict=args.siege_verdict)
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
            scenario=args.scenario,
        )
        with open(args.save_log, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(log), f, default=str, ensure_ascii=False)

    if getattr(completer, "is_open", False):
        err_msg = f"⚠️ 斷路器已跳脫，後端連續失敗：{getattr(completer, 'last_error', '')}"
        print(err_msg, file=sys.stderr)
        print(err_msg)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
