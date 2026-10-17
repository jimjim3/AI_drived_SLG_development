"""Batch evaluation tool across multiple seats and scenarios.

Executes paired comparative evaluation across seats and scenarios with
thread pool concurrency and global total call budget protection.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from typing import Callable, Sequence

from ..agents.backends import CircuitBreakerCompleter
from ..agents.base import FactionAgent
from ..agents.llm_agent import Completer, LLMFactionAgent
from .evaluate import (
    SharedCallCounter,
    evaluate,
    parse_seeds,
    render_markdown,
)
from .run_llm import _parse_extra_body_json, _reorder_command_args, build_completer


def render_summary_markdown(batch_result: dict) -> str:
    """Render a Traditional Chinese summary markdown report for batch evaluation."""
    config = batch_result.get("config", {})
    budget = batch_result.get("total_budget", {})
    summary_rows = batch_result.get("summary", [])

    lines = [
        "# SLG 批次評測總結報告",
        "",
        "## 評測總覽",
        f"- **評測情境**: `{', '.join(config.get('scenarios', []))}`",
        f"- **評測席位**: `{', '.join(config.get('seats', []))}`",
        f"- **評測種子**: `{config.get('seeds', [])}`",
        f"- **每局回合數**: {config.get('turns', 20)}",
        f"- **平行工作緒 (Workers)**: {config.get('workers', 1)}",
        f"- **總呼叫預算**: {budget.get('max_calls') if budget.get('max_calls') is not None else '無上限'}",
        f"- **總使用呼叫數**: {budget.get('calls_used', 0)}{' (已中止（預算耗盡）)' if budget.get('stopped_early') else ''}",
        "",
        "## 總表",
        "",
        "| 組合 | 情境 | 席位 | 席位勝率差 | 兵力差 | 城數差 | 接受率 | 攻城 (嘗試/成功) | 呼叫數 | Tokens | 是否中止 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in summary_rows:
        combo = row.get("combination", "")
        scen = row.get("scenario", "")
        seat = row.get("seat", "")
        wr_delta = f"{row.get('win_rate_delta', 0.0):+.1%}"
        t_delta = f"{row.get('mean_troops_delta', 0.0):+.1f}"
        c_delta = f"{row.get('mean_cities_delta', 0.0):+.2f}"
        acc_rate = (
            f"{row['orders_accept_rate']:.1%}"
            if row.get("orders_accept_rate") is not None
            else "N/A"
        )
        siege_str = f"{row.get('siege_attempts', 0)} / {row.get('siege_captured', 0)}"
        calls_str = str(row.get("calls", 0))
        tokens_str = f"{row.get('est_tokens', 0):,}"
        is_aborted = "是" if row.get("aborted", False) else "否"

        lines.append(
            f"| {combo} | {scen} | {seat} | {wr_delta} | {t_delta} | {c_delta} | {acc_rate} | {siege_str} | {calls_str} | {tokens_str} | {is_aborted} |"
        )

    lines.append("")
    return "\n".join(lines)


def batch_evaluate(
    seats: Sequence[str],
    scenarios: Sequence[str],
    seeds: Sequence[int],
    turns: int = 20,
    completer_builder: Callable[[], Completer] | None = None,
    agent_factory_builder: Callable[[str, str], Callable[..., FactionAgent]] | None = None,
    baseline_style: str = "balanced",
    max_calls: int | None = None,
    max_consecutive_errors: int = 3,
    api_key_env: str | None = None,
    outdir: str | None = None,
    workers: int = 1,
) -> dict:
    """Run batch comparative evaluations across combinations of scenarios and seats."""
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    shared_counter = SharedCallCounter(max_calls=max_calls)
    combos = [(scen, seat) for scen in scenarios for seat in seats]

    def run_combo(scen: str, seat: str) -> dict:
        if agent_factory_builder is not None:
            factory = agent_factory_builder(scen, seat)
        elif completer_builder is not None:
            comp = completer_builder()
            factory = lambda budget: LLMFactionAgent(budget.wrap(comp))
        else:
            raise ValueError("Neither completer_builder nor agent_factory_builder was provided")

        try:
            res = evaluate(
                seeds=seeds,
                turns=turns,
                seat=seat,
                agent_factory=factory,
                baseline_style=baseline_style,
                max_calls=max_calls,
                max_consecutive_errors=max_consecutive_errors,
                api_key_env=api_key_env,
                scenario=scen,
                shared_counter=shared_counter,
            )
        except Exception as exc:
            res = {
                "per_seed": [],
                "summary": {
                    "seat": seat,
                    "scenario": scen,
                    "seeds": [],
                    "planned_seeds": list(seeds),
                    "baseline_win_rate": 0.0,
                    "experiment_win_rate": 0.0,
                    "win_rate_delta": 0.0,
                    "mean_cities_delta": 0.0,
                    "mean_troops_delta": 0.0,
                    "orders_accept_rate": None,
                    "plan_failure_rate": 1.0,
                    "delegated_per_turn": 0.0,
                    "calls": 0,
                    "est_tokens": 0,
                    "parse_failures": 0,
                    "errors": 1,
                    "normalized_params": 0,
                    "diagnostics": {},
                },
                "budget": {
                    "max_calls": max_calls,
                    "calls_used": 0,
                    "stopped_early": True,
                },
                "aborted": True,
                "abort_reason": str(exc),
                "error_samples": [str(exc)[:300]],
            }

        secret_val = os.environ.get(api_key_env) if api_key_env else None

        if outdir:
            combo_md = render_markdown(res)
            if secret_val:
                combo_md = combo_md.replace(secret_val, "[REDACTED]")
            md_path = os.path.join(outdir, f"{scen}__{seat}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(combo_md)

            combo_json_str = json.dumps(res, ensure_ascii=False, indent=2)
            if secret_val:
                combo_json_str = combo_json_str.replace(secret_val, "[REDACTED]")
            json_path = os.path.join(outdir, f"{scen}__{seat}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(combo_json_str)

        return res

    results_by_combo: dict[tuple[str, str], dict] = {}
    if workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_combo = {
                executor.submit(run_combo, scen, seat): (scen, seat)
                for scen, seat in combos
            }
            for future in concurrent.futures.as_completed(future_to_combo):
                combo = future_to_combo[future]
                try:
                    results_by_combo[combo] = future.result()
                except Exception as exc:
                    results_by_combo[combo] = {
                        "per_seed": [],
                        "summary": {"seat": combo[1], "scenario": combo[0]},
                        "budget": {"max_calls": max_calls, "calls_used": 0, "stopped_early": True},
                        "aborted": True,
                        "abort_reason": str(exc),
                        "error_samples": [str(exc)[:300]],
                    }
    else:
        for scen, seat in combos:
            results_by_combo[(scen, seat)] = run_combo(scen, seat)

    summary_rows = []
    combinations_dict = {}

    for scen, seat in combos:
        res = results_by_combo[(scen, seat)]
        s = res.get("summary", {})
        diag = s.get("diagnostics", {})
        exp_siege = diag.get("siege_outcomes", {}).get("experiment", {})
        attempts = int(exp_siege.get("attempts", 0))
        captured = int(exp_siege.get("captured", 0))

        is_aborted = res.get("aborted", False) or res.get("budget", {}).get("stopped_early", False)

        row = {
            "combination": f"{scen}__{seat}",
            "scenario": scen,
            "seat": seat,
            "win_rate_delta": s.get("win_rate_delta", 0.0),
            "mean_troops_delta": s.get("mean_troops_delta", 0.0),
            "mean_cities_delta": s.get("mean_cities_delta", 0.0),
            "orders_accept_rate": s.get("orders_accept_rate"),
            "siege_attempts": attempts,
            "siege_captured": captured,
            "calls": s.get("calls", 0),
            "est_tokens": s.get("est_tokens", 0),
            "aborted": is_aborted,
            "abort_reason": res.get("abort_reason"),
            "stopped_early": res.get("budget", {}).get("stopped_early", False),
            "summary": s,
            "details": res,
        }
        summary_rows.append(row)
        combinations_dict[f"{scen}__{seat}"] = row

    batch_result = {
        "config": {
            "seats": list(seats),
            "scenarios": list(scenarios),
            "seeds": list(seeds),
            "turns": turns,
            "workers": workers,
        },
        "total_budget": {
            "max_calls": max_calls,
            "calls_used": shared_counter.calls_used,
            "stopped_early": shared_counter.stopped_early,
        },
        "summary": summary_rows,
        "results": summary_rows,
        "combinations": combinations_dict,
    }

    secret_val = os.environ.get(api_key_env) if api_key_env else None
    summary_md = render_summary_markdown(batch_result)
    if secret_val:
        summary_md = summary_md.replace(secret_val, "[REDACTED]")

    summary_json_str = json.dumps(batch_result, ensure_ascii=False, indent=2)
    if secret_val:
        summary_json_str = summary_json_str.replace(secret_val, "[REDACTED]")

    if outdir:
        with open(os.path.join(outdir, "SUMMARY.md"), "w", encoding="utf-8") as f:
            f.write(summary_md)
        with open(os.path.join(outdir, "SUMMARY.json"), "w", encoding="utf-8") as f:
            f.write(summary_json_str)

    return batch_result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Batch SLG evaluation tool across multiple seats and scenarios.",
    )
    parser.add_argument(
        "--seats",
        type=str,
        default="faction_1,faction_2,faction_3",
        help="Comma-separated faction seats (default: faction_1,faction_2,faction_3)",
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default="default,advantage",
        help="Comma-separated scenarios (default: default,advantage)",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="0-9",
        help="Seeds range/list, e.g. 0-9 or 1,3,5 (default: 0-9)",
    )
    parser.add_argument("--turns", type=int, default=20, help="Turns per game (default: 20)")
    parser.add_argument("--max-calls", type=int, default=None, help="Global total LLM call budget (default: None)")
    parser.add_argument("--baseline-style", type=str, default="balanced", help="Baseline rule-based style (default: balanced)")
    parser.add_argument("--outdir", type=str, default="./eval_results", help="Directory to output reports (default: ./eval_results)")
    parser.add_argument("--workers", type=int, default=1, help="Parallel worker threads (default: 1)")
    parser.add_argument("--demo", action="store_true", help="Use DemoCompleter backend")
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
        "--extra-body-json",
        type=_parse_extra_body_json,
        default=None,
        help="Additional JSON object to merge into OpenAI request body",
    )
    parser.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        help="Max consecutive errors before circuit breaker opens (default: 3)",
    )
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=None,
        help="Subprocess command for CommandCompleter",
    )

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    known = {
        "--seats",
        "--scenarios",
        "--seeds",
        "--turns",
        "--max-calls",
        "--baseline-style",
        "--outdir",
        "--workers",
        "--demo",
        "--openai-base-url",
        "--model",
        "--api-key-env",
        "--extra-body-json",
        "--max-consecutive-errors",
        "--http-retries",
        "--min-interval",
        "--http-timeout",
    }
    processed_argv = _reorder_command_args(raw_argv, known)
    args = parser.parse_args(processed_argv)

    has_command = getattr(args, "command", None) is not None and len(args.command) > 0
    has_openai = bool(getattr(args, "openai_base_url", None) and getattr(args, "model", None))
    has_demo = bool(getattr(args, "demo", False))
    if not (has_demo or has_command or has_openai):
        parser.print_usage(sys.stderr)
        sys.exit(1)

    try:
        seeds = parse_seeds(args.seeds)
    except ValueError as exc:
        print(f"Error parsing seeds: {exc}", file=sys.stderr)
        sys.exit(2)

    seats = [s.strip() for s in args.seats.split(",") if s.strip()]
    if not seats:
        print("Error: --seats cannot be empty", file=sys.stderr)
        sys.exit(2)

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    if not scenarios:
        print("Error: --scenarios cannot be empty", file=sys.stderr)
        sys.exit(2)

    completer_builder = lambda: build_completer(args)

    result = batch_evaluate(
        seats=seats,
        scenarios=scenarios,
        seeds=seeds,
        turns=args.turns,
        completer_builder=completer_builder,
        baseline_style=args.baseline_style,
        max_calls=args.max_calls,
        max_consecutive_errors=args.max_consecutive_errors,
        api_key_env=args.api_key_env,
        outdir=args.outdir,
        workers=args.workers,
    )

    secret_val = os.environ.get(args.api_key_env) if args.api_key_env else None
    summary_md = render_summary_markdown(result)
    if secret_val:
        summary_md = summary_md.replace(secret_val, "[REDACTED]")

    print(summary_md)


if __name__ == "__main__":
    main()
