"""Comparative evaluation script (LLM vs Rule-Based baseline) with call budget protection."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from typing import Callable, Sequence

from ..agents.base import FactionAgent
from ..agents.llm_agent import Completer, LLMFactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..engine.initial_state import build_initial_state
from .headless import run_headless
from .run_llm import build_completer


def parse_seeds(s: str) -> list[int]:
    """Parse seed specification string into a list of integers.

    Supports comma-separated integers and inclusive ranges:
      - "0-3" -> [0, 1, 2, 3]
      - "1,3,5" -> [1, 3, 5]
      - "0-2,5,7-8" -> [0, 1, 2, 5, 7, 8]
    Raises ValueError on invalid formats or empty input.
    """
    s = s.strip()
    if not s:
        raise ValueError("Seed string cannot be empty")
    parts = [p.strip() for p in s.split(",")]
    seeds: list[int] = []
    for part in parts:
        if not part:
            raise ValueError(f"Invalid empty seed component in {s!r}")
        if "-" in part:
            range_parts = part.split("-")
            if len(range_parts) != 2:
                raise ValueError(f"Invalid range specification: {part!r}")
            try:
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
            except ValueError as exc:
                raise ValueError(f"Non-integer in range: {part!r}") from exc
            if start > end:
                raise ValueError(f"Range start must be <= end: {part!r}")
            seeds.extend(range(start, end + 1))
        else:
            try:
                seeds.append(int(part))
            except ValueError as exc:
                raise ValueError(f"Non-integer seed: {part!r}") from exc
    return seeds


class CallBudget:
    """Tracks and enforces LLM call budget.

    Provides ``wrap(completer)`` to wrap a completer function so that calls
    are counted toward the budget. When ``max_calls`` is reached, subsequent
    calls raise ``RuntimeError("call budget exceeded")``.
    """

    def __init__(self, max_calls: int | None = None) -> None:
        self.max_calls = max_calls
        self.calls_used = 0
        self.stopped_early = False

    def wrap(self, completer: Completer) -> Completer:
        def wrapped(system: str, user: str) -> str:
            if self.max_calls is not None and self.calls_used >= self.max_calls:
                self.stopped_early = True
                raise RuntimeError("call budget exceeded")
            self.calls_used += 1
            return completer(system, user)

        return wrapped


def _instantiate_agent(factory: Callable, budget: CallBudget) -> FactionAgent:
    """Instantiate a FactionAgent from factory, passing budget if accepted."""
    try:
        sig = inspect.signature(factory)
        if len(sig.parameters) == 0:
            return factory()
        return factory(budget)
    except (ValueError, TypeError):
        try:
            return factory(budget)
        except TypeError:
            return factory()


def evaluate(
    seeds: Sequence[int],
    turns: int = 20,
    seat: str = "faction_2",
    agent_factory: Callable[..., FactionAgent] | None = None,
    baseline_style: str = "balanced",
    max_calls: int | None = None,
) -> dict:
    """Run paired comparative games (baseline vs experiment) across seeds.

    Parameters
    ----------
    seeds : Sequence[int]
        Random seeds to simulate.
    turns : int
        Simulation turns per game (default: 20).
    seat : str
        Faction identifier to evaluate (default: "faction_2").
    agent_factory : Callable
        Factory producing the experimental ``FactionAgent`` for ``seat``.
        Accepts a ``CallBudget`` instance providing ``wrap(completer)``,
        or takes 0 arguments.
    baseline_style : str
        Style for RuleBasedAgent in baseline games and non-experimental factions.
    max_calls : int or None
        Maximum cumulative LLM calls allowed across all evaluated seeds.
        If cumulative calls reach or exceed this limit before a seed begins,
        further seeds are skipped and ``budget.stopped_early`` is set to True.
        Inside a game, ``budget.wrap(completer)`` blocks excess calls by
        raising ``RuntimeError("call budget exceeded")``.

    Returns
    -------
    dict
        A JSON-serializable dictionary with keys ``per_seed``, ``summary``,
        and ``budget``.
    """
    if agent_factory is None:
        raise ValueError("agent_factory must be provided")

    seed_list = list(seeds)
    per_seed: list[dict] = []
    budget = CallBudget(max_calls=max_calls)
    total_exp_turns = 0

    state_template = build_initial_state()
    faction_ids = sorted(state_template.factions)

    for seed in seed_list:
        cumulative_usage_calls = sum(
            s["experiment"]["usage"].get("calls", 0) for s in per_seed
        )
        if max_calls is not None and (
            budget.calls_used >= max_calls
            or (budget.calls_used == 0 and cumulative_usage_calls >= max_calls)
        ):
            budget.stopped_early = True
            break

        # 1. Baseline game: all factions rule-based
        baseline_agents = {
            fid: RuleBasedAgent(baseline_style) for fid in faction_ids
        }
        baseline_res = run_headless(
            seed=seed, turns=turns, agents_by_faction=baseline_agents
        )
        baseline_seat_cities = len(baseline_res.final_state.cities_of(seat))
        baseline_seat_troops = sum(
            c.troops for c in baseline_res.final_state.cities_of(seat)
        )

        # 2. Experiment game: seat faction uses agent_factory
        exp_agent = _instantiate_agent(agent_factory, budget)
        exp_agents = {
            fid: RuleBasedAgent(baseline_style) for fid in faction_ids
        }
        exp_agents[seat] = exp_agent
        exp_res = run_headless(
            seed=seed, turns=turns, agents_by_faction=exp_agents
        )
        exp_seat_cities = len(exp_res.final_state.cities_of(seat))
        exp_seat_troops = sum(
            c.troops for c in exp_res.final_state.cities_of(seat)
        )
        exp_usage = dict(
            exp_res.usage.get(seat, getattr(exp_agent, "usage", {}))
        )
        total_exp_turns += exp_res.final_state.turn

        per_seed.append(
            {
                "seed": seed,
                "baseline": {
                    "winner": baseline_res.winner,
                    "cities": baseline_seat_cities,
                    "troops": baseline_seat_troops,
                },
                "experiment": {
                    "winner": exp_res.winner,
                    "cities": exp_seat_cities,
                    "troops": exp_seat_troops,
                    "stats": dict(exp_res.stats),
                    "usage": exp_usage,
                },
            }
        )

    n_seeds = len(per_seed)
    if n_seeds > 0:
        baseline_wins = sum(
            1 for s in per_seed if s["baseline"]["winner"] == seat
        )
        exp_wins = sum(
            1 for s in per_seed if s["experiment"]["winner"] == seat
        )
        baseline_win_rate = baseline_wins / n_seeds
        experiment_win_rate = exp_wins / n_seeds
        win_rate_delta = experiment_win_rate - baseline_win_rate
        mean_cities_delta = (
            sum(
                s["experiment"]["cities"] - s["baseline"]["cities"]
                for s in per_seed
            )
            / n_seeds
        )
        mean_troops_delta = (
            sum(
                s["experiment"]["troops"] - s["baseline"]["troops"]
                for s in per_seed
            )
            / n_seeds
        )
    else:
        baseline_win_rate = 0.0
        experiment_win_rate = 0.0
        win_rate_delta = 0.0
        mean_cities_delta = 0.0
        mean_troops_delta = 0.0

    total_orders = sum(
        s["experiment"]["stats"].get("orders", 0) for s in per_seed
    )
    total_rejected = sum(
        s["experiment"]["stats"].get("orders_rejected", 0) for s in per_seed
    )
    if total_orders == 0:
        orders_accept_rate = None
    else:
        orders_accept_rate = total_orders / (total_orders + total_rejected)

    total_plan_failures = sum(
        s["experiment"]["stats"].get("plan_failures", 0) for s in per_seed
    )
    plan_failure_rate = (
        total_plan_failures / total_exp_turns if total_exp_turns > 0 else 0.0
    )

    total_delegated = sum(
        s["experiment"]["stats"].get("delegated", 0) for s in per_seed
    )
    delegated_per_turn = (
        total_delegated / total_exp_turns if total_exp_turns > 0 else 0.0
    )

    usage_calls = sum(
        s["experiment"]["usage"].get("calls", 0) for s in per_seed
    )
    calls = usage_calls if (usage_calls > 0 or not budget.calls_used) else budget.calls_used
    est_tokens = sum(
        (
            s["experiment"]["usage"].get("prompt_chars", 0)
            + s["experiment"]["usage"].get("response_chars", 0)
        )
        // 2
        for s in per_seed
    )
    parse_failures = sum(
        s["experiment"]["usage"].get("parse_failures", 0) for s in per_seed
    )
    errors = sum(
        s["experiment"]["usage"].get("errors", 0) for s in per_seed
    )

    summary = {
        "seat": seat,
        "seeds": [s["seed"] for s in per_seed],
        "baseline_win_rate": baseline_win_rate,
        "experiment_win_rate": experiment_win_rate,
        "win_rate_delta": win_rate_delta,
        "mean_cities_delta": mean_cities_delta,
        "mean_troops_delta": mean_troops_delta,
        "orders_accept_rate": orders_accept_rate,
        "plan_failure_rate": plan_failure_rate,
        "delegated_per_turn": delegated_per_turn,
        "calls": calls,
        "est_tokens": est_tokens,
        "parse_failures": parse_failures,
        "errors": errors,
    }

    budget_calls_used = (
        budget.calls_used
        if (budget.calls_used > 0 or max_calls == 0)
        else usage_calls
    )

    return {
        "per_seed": per_seed,
        "summary": summary,
        "budget": {
            "max_calls": max_calls,
            "calls_used": budget_calls_used,
            "stopped_early": budget.stopped_early,
        },
    }


def render_markdown(result: dict) -> str:
    """Render a Traditional Chinese markdown report from evaluation results."""
    summary = result["summary"]
    budget = result["budget"]
    per_seed = result["per_seed"]

    lines = []
    lines.append("# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)")
    lines.append("")
    lines.append("## 評測設定")
    lines.append(f"- **評測席位 (Seat)**: `{summary['seat']}`")
    lines.append(f"- **評測種子數**: {len(summary['seeds'])} (種子: `{summary['seeds']}`)")
    lines.append(
        f"- **呼叫預算 (Max Calls)**: {budget['max_calls'] if budget['max_calls'] is not None else '無上限'}"
    )
    lines.append(
        f"- **已使用呼叫數 (Calls Used)**: {budget['calls_used']}"
        + (" (⚠️ 預算耗盡，提前終止)" if budget["stopped_early"] else " (未觸發提前終止)")
    )
    lines.append("")
    lines.append("## 評測摘要")
    lines.append("")
    lines.append("| 指標 | 數值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 評測席位 (seat) | {summary['seat']} |")
    lines.append(f"| 基準線勝率 (baseline_win_rate) | {summary['baseline_win_rate']:.1%} |")
    lines.append(f"| 實驗組勝率 (experiment_win_rate) | {summary['experiment_win_rate']:.1%} |")
    lines.append(f"| 勝率差異 (win_rate_delta) | {summary['win_rate_delta']:+.1%} |")
    lines.append(f"| 平均城池差 (mean_cities_delta) | {summary['mean_cities_delta']:+.2f} |")
    lines.append(f"| 平均兵力差 (mean_troops_delta) | {summary['mean_troops_delta']:+.1f} |")
    accept_rate_str = (
        f"{summary['orders_accept_rate']:.1%}"
        if summary["orders_accept_rate"] is not None
        else "N/A (無指令)"
    )
    lines.append(f"| 指令接受率 (orders_accept_rate) | {accept_rate_str} |")
    lines.append(f"| 計劃失敗率 (plan_failure_rate) | {summary['plan_failure_rate']:.1%} |")
    lines.append(f"| 每回合委任數 (delegated_per_turn) | {summary['delegated_per_turn']:.2f} |")
    lines.append(f"| LLM 呼叫次數 (calls) | {summary['calls']} |")
    lines.append(f"| 估計 Token 數 (est_tokens) | {summary['est_tokens']} |")
    lines.append(f"| 解析失敗次數 (parse_failures) | {summary['parse_failures']} |")
    lines.append(f"| 呼叫錯誤次數 (errors) | {summary['errors']} |")
    lines.append("")
    lines.append("## 逐種子明細")
    lines.append("")
    lines.append(
        "| 種子 | 基準勝者 | 基準城數/兵力 | 實驗勝者 | 實驗城數/兵力 | 城池差 | 兵力差 | 呼叫數 | 成功/被拒/委任 |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    for s in per_seed:
        seed = s["seed"]
        b = s["baseline"]
        e = s["experiment"]
        b_win = b["winner"] or "無"
        e_win = e["winner"] or "無"
        b_cp = f"{b['cities']} 城 / {b['troops']} 兵"
        e_cp = f"{e['cities']} 城 / {e['troops']} 兵"
        c_diff = e["cities"] - b["cities"]
        t_diff = e["troops"] - b["troops"]
        calls_count = e["usage"].get("calls", 0)
        st = e.get("stats", {})
        orders = st.get("orders", 0)
        rejected = st.get("orders_rejected", 0)
        delegated = st.get("delegated", 0)
        stats_str = f"{orders} / {rejected} / {delegated}"
        lines.append(
            f"| {seed} | {b_win} | {b_cp} | {e_win} | {e_cp} | {c_diff:+d} | {t_diff:+d} | {calls_count} | {stats_str} |"
        )
    lines.append("")
    lines.append("## 預算保護")
    lines.append(f"- **max_calls**: {budget['max_calls']}")
    lines.append(f"- **calls_used**: {budget['calls_used']}")
    lines.append(f"- **stopped_early**: {'是 (True)' if budget['stopped_early'] else '否 (False)'}")
    lines.append("")
    lines.append("## 限制說明與注意事項")
    lines.append("> [!NOTE]")
    lines.append("> **同座位比較、樣本數小時差異不具統計顯著性**。")
    lines.append(">")
    lines.append(
        "> 1. **同座位比較之必要性**：各勢力在初始地緣、將領與兵力配置上存在結構性差異（例如 faction_1 曹操勢力結構上較強），不可直接比較各勢力勝率，必須比較同座位、同種子下 LLM 與規則 AI 的差異。"
    )
    lines.append(
        "> 2. **統計顯著性**：SLG 模擬包含隨機事件與連鎖決策效應，當評測種子數量較少時，指標差異易受單局偶發狀況影響，不具統計顯著性。建議以較多種子（例如 20 個以上）進行正式評估。"
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run comparative SLG evaluation (LLM vs Rule-based baseline) with call budget protection."
    )
    parser.add_argument("--seat", type=str, default="faction_2", help="Faction seat to evaluate (default: faction_2)")
    parser.add_argument("--seeds", type=str, default="0-4", help="Seeds range/list, e.g. 0-9 or 1,3,5 (default: 0-4)")
    parser.add_argument("--turns", type=int, default=20, help="Turns per game (default: 20)")
    parser.add_argument("--max-calls", type=int, default=60, help="Maximum LLM call budget (default: 60)")
    parser.add_argument("--baseline-style", type=str, default="balanced", help="Baseline rule-based style (default: balanced)")
    parser.add_argument("--out", type=str, default=None, help="Output path for markdown report (and .json)")
    parser.add_argument("--demo", action="store_true", help="Use DemoCompleter backend")
    parser.add_argument("--openai-base-url", type=str, default=None, help="OpenAI-compatible base URL")
    parser.add_argument("--model", type=str, default=None, help="OpenAI model name")
    parser.add_argument("--api-key-env", type=str, default=None, help="Env var name for API key")
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

    try:
        seeds = parse_seeds(args.seeds)
    except ValueError as exc:
        print(f"Error parsing seeds: {exc}", file=sys.stderr)
        sys.exit(2)

    agent_factory = lambda budget: LLMFactionAgent(budget.wrap(completer))

    result = evaluate(
        seeds=seeds,
        turns=args.turns,
        seat=args.seat,
        agent_factory=agent_factory,
        baseline_style=args.baseline_style,
        max_calls=args.max_calls,
    )

    report_md = render_markdown(result)

    secret_val = os.environ.get(args.api_key_env) if args.api_key_env else None
    if secret_val:
        report_md = report_md.replace(secret_val, "[REDACTED]")

    if args.out:
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report_md)
        if not args.out.endswith(".md"):
            with open(f"{args.out}.md", "w", encoding="utf-8") as f:
                f.write(report_md)

        json_str = json.dumps(result, ensure_ascii=False, indent=2)
        if secret_val:
            json_str = json_str.replace(secret_val, "[REDACTED]")

        with open(f"{args.out}.json", "w", encoding="utf-8") as f:
            f.write(json_str)
        if args.out.endswith(".md"):
            alt_json_path = args.out[:-3] + ".json"
            if alt_json_path != f"{args.out}.json":
                with open(alt_json_path, "w", encoding="utf-8") as f:
                    f.write(json_str)

    print(report_md)


if __name__ == "__main__":
    main()
