"""Comparative evaluation script (LLM vs Rule-Based baseline) with call budget protection.

Exit code is non-zero (1) if the evaluation is aborted (e.g. circuit breaker tripped).
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import sys
import threading
from typing import Callable, Sequence

from ..agents.backends import (
    BackendUnavailable,
    CircuitBreakerCompleter,
    ConfigError,
)
from ..agents.base import FactionAgent
from ..agents.llm_agent import Completer, LLMFactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..engine.initial_state import build_initial_state
from .headless import run_headless
from .run_llm import _parse_extra_body_json, build_completer


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


class SharedCallCounter:
    """Thread-safe shared call counter for multi-seat/multi-scenario evaluations."""

    def __init__(self, max_calls: int | None = None) -> None:
        self.max_calls = max_calls
        self.calls_used = 0
        self.stopped_early = False
        self._lock = threading.Lock()

    def check_and_record(self) -> bool:
        with self._lock:
            if self.max_calls is not None and self.calls_used >= self.max_calls:
                self.stopped_early = True
                return False
            self.calls_used += 1
            return True

    def check_exceeded(self) -> bool:
        with self._lock:
            if self.max_calls is not None and self.calls_used >= self.max_calls:
                self.stopped_early = True
                return True
            return False

    def increment(self) -> None:
        with self._lock:
            self.calls_used += 1
            if self.max_calls is not None and self.calls_used >= self.max_calls:
                self.stopped_early = True

    def refund(self) -> None:
        with self._lock:
            if self.calls_used > 0:
                self.calls_used -= 1


class CallBudget:
    """Tracks and enforces LLM call budget.

    Provides ``wrap(completer)`` to wrap a completer function so that calls
    are counted toward the budget. When ``max_calls`` is reached, subsequent
    calls raise ``RuntimeError("call budget exceeded")``.
    """

    def __init__(
        self,
        max_calls: int | None = None,
        max_consecutive_errors: int = 3,
        shared_counter: SharedCallCounter | None = None,
    ) -> None:
        self.max_calls = max_calls
        self.max_consecutive_errors = max_consecutive_errors
        self.calls_used = 0
        self.stopped_early = False
        self.circuit_breaker: CircuitBreakerCompleter | None = None
        self.shared_counter = shared_counter

    def wrap(self, completer: Completer) -> Completer:
        if isinstance(completer, CircuitBreakerCompleter):
            cb = completer
        elif self.circuit_breaker is not None and getattr(self.circuit_breaker, "inner", None) is completer:
            cb = self.circuit_breaker
        else:
            cb = CircuitBreakerCompleter(completer, max_consecutive_errors=self.max_consecutive_errors)

        self.circuit_breaker = cb

        def wrapped(system: str, user: str) -> str:
            if cb.is_open:
                return cb(system, user)
            if self.shared_counter is not None:
                if not self.shared_counter.check_and_record():
                    self.stopped_early = True
                    raise RuntimeError("call budget exceeded")
            elif self.max_calls is not None and self.calls_used >= self.max_calls:
                self.stopped_early = True
                raise RuntimeError("call budget exceeded")
            try:
                res = cb(system, user)
            except ConfigError:
                if self.shared_counter is not None:
                    self.shared_counter.refund()
                raise
            except Exception:
                self.calls_used += 1
                raise
            self.calls_used += 1
            return res

        wrapped.circuit_breaker = cb  # type: ignore[attr-defined]
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


def _compute_officer_loss_curve(
    initial_count: int,
    actual_turns: int,
    incidents: Sequence,
    seat: str,
) -> list[int]:
    """Compute officer count of seat at the end of each turn.

    Length equals actual_turns. Computed from initial living officer count and
    per-turn defection events in GameResult.incidents (net change from officers
    defecting away from seat vs defecting to seat).
    """
    curr = initial_count
    curve: list[int] = []
    for t in range(1, actual_turns + 1):
        for inc in incidents:
            if getattr(inc, "turn", 0) == t and getattr(inc, "action", "") == "defect":
                orig_fid = getattr(inc, "faction_id", "")
                detail = getattr(inc, "detail", "") or ""
                if orig_fid == seat:
                    curr -= 1
                elif bool(re.search(rf"->\s*{re.escape(seat)}\b", detail)):
                    curr += 1
        curve.append(curr)
    return curve


def _compute_rejection_reasons(flogs: Sequence, seat: str, top_n: int = 3) -> list[dict[str, object]]:
    """Compute top N normalized rejection reasons for seat from faction logs."""
    rej_counts: dict[str, int] = {}
    for flog in flogs:
        if getattr(flog, "faction_id", "") == seat:
            for rej in getattr(flog, "rejected", ()):
                reason = rej[2] if len(rej) > 2 else str(rej)
                norm_r = re.sub(r"\d+", "N", reason)
                rej_counts[norm_r] = rej_counts.get(norm_r, 0) + 1
    sorted_rej = sorted(rej_counts.items(), key=lambda x: (-x[1], x[0]))[:top_n]
    return [{"reason": r, "count": c} for r, c in sorted_rej]


def _compute_game_diagnostics(
    res,
    initial_state,
    seat: str,
) -> dict[str, object]:
    """Compute diagnostic metrics for a single game run."""
    action_counts: dict[str, int] = {}
    for e in res.events:
        if getattr(e, "faction_id", "") == seat:
            act = getattr(e, "action", "")
            if act:
                action_counts[act] = action_counts.get(act, 0) + 1

    defect_count = sum(
        1
        for inc in res.incidents
        if getattr(inc, "action", "") == "defect" and getattr(inc, "faction_id", "") == seat
    )
    disobey_count = res.stats.get("disobeyed")
    if disobey_count is None:
        disobey_count = sum(
            1
            for e in res.events
            if getattr(e, "faction_id", "") == seat and "抗旨" in (getattr(e, "detail", "") or "")
        )
    init_officers = len(
        [o for o in initial_state.officers.values() if o.faction_id == seat and o.is_alive]
    )
    final_living = [
        o for o in res.final_state.officers.values() if o.faction_id == seat and o.is_alive
    ]
    final_officers = len(final_living)
    final_avg_loyalty = (
        round(sum(o.loyalty for o in final_living) / len(final_living), 2)
        if final_living
        else 0.0
    )
    incidents_data = {
        "deflections": defect_count,
        "defect_count": defect_count,
        "disobeyed": disobey_count,
        "disobey_count": disobey_count,
        "initial_officers": init_officers,
        "final_officers": final_officers,
        "final_avg_loyalty": final_avg_loyalty,
    }

    actual_turns = res.final_state.turn
    curve = _compute_officer_loss_curve(
        initial_count=init_officers,
        actual_turns=actual_turns,
        incidents=res.incidents,
        seat=seat,
    )

    flogs = res.log.faction_logs if res.log else ()
    rejection_reasons = _compute_rejection_reasons(flogs, seat=seat, top_n=3)

    seat_flogs = [f for f in flogs if getattr(f, "faction_id", "") == seat]
    total_named = sum(len(getattr(f, "ordered", ())) for f in seat_flogs)
    total_delegated = sum(len(getattr(f, "delegated", ())) for f in seat_flogs)
    if actual_turns > 0:
        avg_named = round(total_named / actual_turns, 2)
        avg_delegated = round(total_delegated / actual_turns, 2)
    else:
        avg_named = 0.0
        avg_delegated = 0.0
    named_per_turn = {
        "named": avg_named,
        "delegated": avg_delegated,
        "ordered": avg_named,
    }

    siege_attempts = 0
    siege_captured = 0
    siege_repelled = 0
    for e in res.events:
        if getattr(e, "faction_id", "") == seat and getattr(e, "action", "") == "siege":
            siege_attempts += 1
            if getattr(e, "captured_city", None) is not None:
                siege_captured += 1
            else:
                siege_repelled += 1

    siege_outcomes = {
        "attempts": siege_attempts,
        "captured": siege_captured,
        "repelled": siege_repelled,
    }

    return {
        "action_counts": dict(sorted(action_counts.items())),
        "siege_outcomes": siege_outcomes,
        "incidents": incidents_data,
        "officer_loss_curve": curve,
        "rejection_reasons": rejection_reasons,
        "named_per_turn": named_per_turn,
        "actual_turns": actual_turns,
    }


def _aggregate_diagnostics(per_seed: list[dict], total_exp_turns: int) -> dict[str, object]:
    """Aggregate per-seed diagnostic metrics across all evaluated seeds."""
    n = len(per_seed)
    base_actions: dict[str, int] = {}
    exp_actions: dict[str, int] = {}
    all_rejection_counts: dict[str, int] = {}
    total_named = 0
    total_delegated = 0

    base_defects = 0
    exp_defects = 0
    base_disobeys = 0
    exp_disobeys = 0
    base_init_officers = 0
    exp_init_officers = 0
    base_final_officers_sum = 0
    exp_final_officers_sum = 0
    base_loyalty_sum = 0.0
    exp_loyalty_sum = 0.0

    base_siege = {"attempts": 0, "captured": 0, "repelled": 0}
    exp_siege = {"attempts": 0, "captured": 0, "repelled": 0}

    curves: list[list[int]] = []

    for s in per_seed:
        diag = s.get("diagnostics", {})
        ac = diag.get("action_counts", {})
        for act, cnt in ac.get("baseline", {}).items():
            base_actions[act] = base_actions.get(act, 0) + cnt
        for act, cnt in ac.get("experiment", {}).items():
            exp_actions[act] = exp_actions.get(act, 0) + cnt

        so = diag.get("siege_outcomes", {})
        b_so = so.get("baseline", {})
        e_so = so.get("experiment", {})
        base_siege["attempts"] += int(b_so.get("attempts", 0))
        base_siege["captured"] += int(b_so.get("captured", 0))
        base_siege["repelled"] += int(b_so.get("repelled", 0))
        exp_siege["attempts"] += int(e_so.get("attempts", 0))
        exp_siege["captured"] += int(e_so.get("captured", 0))
        exp_siege["repelled"] += int(e_so.get("repelled", 0))

        for r_item in diag.get("rejection_reasons", []):
            r_str = str(r_item["reason"])
            r_cnt = int(r_item["count"])
            all_rejection_counts[r_str] = all_rejection_counts.get(r_str, 0) + r_cnt

        inc = diag.get("incidents", {})
        b_inc = inc.get("baseline", {})
        e_inc = inc.get("experiment", {})
        base_defects += int(b_inc.get("deflections", 0))
        exp_defects += int(e_inc.get("deflections", 0))
        base_disobeys += int(b_inc.get("disobeyed", 0))
        exp_disobeys += int(e_inc.get("disobeyed", 0))
        base_init_officers = int(b_inc.get("initial_officers", base_init_officers))
        exp_init_officers = int(e_inc.get("initial_officers", exp_init_officers))
        base_final_officers_sum += int(b_inc.get("final_officers", 0))
        exp_final_officers_sum += int(e_inc.get("final_officers", 0))
        base_loyalty_sum += float(b_inc.get("final_avg_loyalty", 0.0))
        exp_loyalty_sum += float(e_inc.get("final_avg_loyalty", 0.0))

        c = diag.get("officer_loss_curve", [])
        if c:
            curves.append(c)

        actual_turns = int(s.get("actual_turns", len(c)))
        npt = diag.get("named_per_turn", {})
        total_named += round(float(npt.get("named", 0.0)) * actual_turns)
        total_delegated += round(float(npt.get("delegated", 0.0)) * actual_turns)

    max_len = max((len(c) for c in curves), default=0)
    avg_curve = []
    for idx in range(max_len):
        vals = [c[idx] for c in curves if len(c) > idx]
        avg_val = round(sum(vals) / len(vals), 2) if vals else 0.0
        avg_curve.append(avg_val)

    sorted_all_reasons = sorted(all_rejection_counts.items(), key=lambda x: (-x[1], x[0]))[:3]
    top_rejection_reasons = [{"reason": r, "count": c} for r, c in sorted_all_reasons]

    if total_exp_turns > 0:
        named_avg = round(total_named / total_exp_turns, 2)
        delegated_avg = round(total_delegated / total_exp_turns, 2)
    else:
        named_avg = 0.0
        delegated_avg = 0.0

    b_final_avg = round(base_final_officers_sum / n, 2) if n else 0.0
    e_final_avg = round(exp_final_officers_sum / n, 2) if n else 0.0
    b_loyalty_avg = round(base_loyalty_sum / n, 2) if n else 0.0
    e_loyalty_avg = round(exp_loyalty_sum / n, 2) if n else 0.0

    return {
        "action_counts": {
            "baseline": dict(sorted(base_actions.items())),
            "experiment": dict(sorted(exp_actions.items())),
        },
        "siege_outcomes": {
            "baseline": base_siege,
            "experiment": exp_siege,
        },
        "incidents": {
            "baseline": {
                "deflections": base_defects,
                "disobeyed": base_disobeys,
                "initial_officers": base_init_officers,
                "final_officers": b_final_avg,
                "final_avg_loyalty": b_loyalty_avg,
            },
            "experiment": {
                "deflections": exp_defects,
                "disobeyed": exp_disobeys,
                "initial_officers": exp_init_officers,
                "final_officers": e_final_avg,
                "final_avg_loyalty": e_loyalty_avg,
            },
            "deflections": exp_defects,
            "defect_count": exp_defects,
            "disobeyed": exp_disobeys,
            "disobey_count": exp_disobeys,
            "initial_officers": exp_init_officers,
            "final_officers": e_final_avg,
            "final_avg_loyalty": e_loyalty_avg,
        },
        "officer_loss_curve": avg_curve,
        "rejection_reasons": top_rejection_reasons,
        "named_per_turn": {
            "named": named_avg,
            "delegated": delegated_avg,
            "ordered": named_avg,
        },
    }


def generate_possible_cause_hint(summary: dict) -> str:
    """Generate diagnostic rule-based possible cause hint without calling LLM."""
    diag = summary.get("diagnostics", {})
    action_counts = diag.get("action_counts", {})
    base_recruit = action_counts.get("baseline", {}).get("recruit", 0)
    exp_recruit = action_counts.get("experiment", {}).get("recruit", 0)

    incidents = diag.get("incidents", {})
    exp_inc = incidents.get("experiment", incidents)
    exp_defect = exp_inc.get("deflections", 0)

    rejection_reasons = diag.get("rejection_reasons", [])

    hints: list[str] = []
    # 1. 徵兵偏少: 實驗組徵兵次數 < 基準線一半
    if base_recruit > 0 and exp_recruit < base_recruit / 2:
        hints.append("LLM 徵兵偏少")

    # 2. 出奔: 出奔數 >= 1
    if exp_defect >= 1:
        hints.append("有武將出奔，檢查冷落機制")

    # 3. 拒絕率 > 10%
    accept_rate = summary.get("orders_accept_rate")
    if accept_rate is not None and (1.0 - accept_rate) > 0.10:
        top_reason = rejection_reasons[0]["reason"] if rejection_reasons else "未知原因"
        hints.append(f"指令被拒比例偏高，主因：{top_reason}")

    # 4. 兵力偏低: 實驗組最終兵力 < 基準線的 80%
    base_troops = summary.get("baseline_troops")
    exp_troops = summary.get("experiment_troops")
    if base_troops is None or exp_troops is None:
        troops_data = diag.get("troops") or summary.get("troops") or {}
        if base_troops is None:
            base_troops = troops_data.get("baseline")
        if exp_troops is None:
            exp_troops = troops_data.get("experiment")
    if (base_troops is None or exp_troops is None) and "per_seed" in summary:
        ps = summary["per_seed"]
        if ps:
            base_troops = sum(s.get("baseline", {}).get("troops", 0) for s in ps)
            exp_troops = sum(s.get("experiment", {}).get("troops", 0) for s in ps)

    if base_troops is not None and exp_troops is not None and base_troops > 0:
        if exp_troops < base_troops * 0.8:
            drop_pct = (base_troops - exp_troops) / base_troops * 100
            if abs(drop_pct - round(drop_pct)) < 1e-5:
                x_str = f"{int(round(drop_pct))}"
            else:
                x_str = f"{drop_pct:.1f}"

            siege_outcomes = diag.get("siege_outcomes", {})
            exp_siege = siege_outcomes.get("experiment", {})
            y = exp_siege.get("captured", 0)
            z = exp_siege.get("attempts", 0)

            hints.append(f"最終兵力明顯低於基準線（-{x_str}%），檢查出征損失（siege 成功率 {y}/{z}）與徵兵")

    if not hints:
        return "表現正常，未見明顯異常。"
    return "；".join(hints)


def evaluate(
    seeds: Sequence[int],
    turns: int = 20,
    seat: str = "faction_2",
    agent_factory: Callable[..., FactionAgent] | None = None,
    baseline_style: str = "balanced",
    max_calls: int | None = None,
    max_consecutive_errors: int = 3,
    api_key_env: str | None = None,
    scenario: str = "default",
    shared_counter: SharedCallCounter | None = None,
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
    max_consecutive_errors : int
        Max consecutive errors before circuit breaker opens (default: 3).
    api_key_env : str or None
        Environment variable name for API key to redact from reports/samples.
    scenario : str
        Initial state scenario name (default: "default").
    shared_counter : SharedCallCounter or None
        Optional shared counter across evaluations.

    Returns
    -------
    dict
        A JSON-serializable dictionary with keys ``per_seed``, ``summary``,
        ``budget``, ``aborted``, ``abort_reason``, and ``error_samples``.
    """
    if agent_factory is None:
        raise ValueError("agent_factory must be provided")

    seed_list = list(seeds)
    per_seed: list[dict] = []
    budget = CallBudget(
        max_calls=max_calls,
        max_consecutive_errors=max_consecutive_errors,
        shared_counter=shared_counter,
    )
    total_exp_turns = 0
    all_error_samples: list[str] = []
    aborted = False
    abort_reason: str | None = None

    state_template = build_initial_state(scenario=scenario)
    faction_ids = sorted(state_template.factions)

    for seed in seed_list:
        if shared_counter is not None and shared_counter.check_exceeded():
            budget.stopped_early = True
            break

        if budget.circuit_breaker is not None and budget.circuit_breaker.is_open:
            aborted = True
            abort_reason = (
                f"後端連續失敗（{budget.circuit_breaker.consecutive_errors} 次）："
                f"{budget.circuit_breaker.last_error}"
            )
            break

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
            seed=seed, turns=turns, agents_by_faction=baseline_agents, scenario=scenario
        )
        baseline_seat_cities = len(baseline_res.final_state.cities_of(seat))
        baseline_seat_troops = sum(
            c.troops for c in baseline_res.final_state.cities_of(seat)
        )

        # 2. Experiment game: seat faction uses agent_factory
        exp_agent = _instantiate_agent(agent_factory, budget)
        if budget.circuit_breaker is None:
            comp = getattr(exp_agent, "_completer", None)
            if isinstance(comp, CircuitBreakerCompleter):
                budget.circuit_breaker = comp
            elif hasattr(comp, "circuit_breaker") and isinstance(comp.circuit_breaker, CircuitBreakerCompleter):
                budget.circuit_breaker = comp.circuit_breaker

        exp_agents = {
            fid: RuleBasedAgent(baseline_style) for fid in faction_ids
        }
        exp_agents[seat] = exp_agent
        exp_res = run_headless(
            seed=seed, turns=turns, agents_by_faction=exp_agents, scenario=scenario
        )
        exp_seat_cities = len(exp_res.final_state.cities_of(seat))
        exp_seat_troops = sum(
            c.troops for c in exp_res.final_state.cities_of(seat)
        )
        exp_usage = dict(
            exp_res.usage.get(seat, getattr(exp_agent, "usage", {}))
        )
        total_exp_turns += exp_res.final_state.turn

        if budget.circuit_breaker is not None and budget.calls_used == 0:
            budget.calls_used = budget.circuit_breaker.real_calls

        for err in getattr(exp_agent, "errors_seen", []):
            if err not in all_error_samples and len(all_error_samples) < 5:
                all_error_samples.append(err)

        base_diag = _compute_game_diagnostics(baseline_res, state_template, seat)
        exp_diag = _compute_game_diagnostics(exp_res, state_template, seat)

        seed_diag = {
            "action_counts": {
                "baseline": base_diag["action_counts"],
                "experiment": exp_diag["action_counts"],
            },
            "siege_outcomes": {
                "baseline": base_diag["siege_outcomes"],
                "experiment": exp_diag["siege_outcomes"],
            },
            "incidents": {
                "baseline": base_diag["incidents"],
                "experiment": exp_diag["incidents"],
                "deflections": exp_diag["incidents"]["deflections"],
                "defect_count": exp_diag["incidents"]["defect_count"],
                "disobeyed": exp_diag["incidents"]["disobeyed"],
                "disobey_count": exp_diag["incidents"]["disobey_count"],
                "initial_officers": exp_diag["incidents"]["initial_officers"],
                "final_officers": exp_diag["incidents"]["final_officers"],
                "final_avg_loyalty": exp_diag["incidents"]["final_avg_loyalty"],
            },
            "officer_loss_curve": exp_diag["officer_loss_curve"],
            "officer_loss_curve_baseline": base_diag["officer_loss_curve"],
            "rejection_reasons": exp_diag["rejection_reasons"],
            "named_per_turn": exp_diag["named_per_turn"],
        }

        per_seed.append(
            {
                "seed": seed,
                "actual_turns": exp_res.final_state.turn,
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
                "diagnostics": seed_diag,
            }
        )

        if budget.circuit_breaker is not None and budget.circuit_breaker.is_open:
            aborted = True
            abort_reason = (
                f"後端連續失敗（{budget.circuit_breaker.consecutive_errors} 次）："
                f"{budget.circuit_breaker.last_error}"
            )
            break

    if budget.circuit_breaker is not None and budget.circuit_breaker.is_open:
        aborted = True
        if abort_reason is None:
            abort_reason = (
                f"後端連續失敗（{budget.circuit_breaker.consecutive_errors} 次）："
                f"{budget.circuit_breaker.last_error}"
            )

    if budget.circuit_breaker is not None and budget.circuit_breaker.last_error:
        if budget.circuit_breaker.last_error not in all_error_samples and len(all_error_samples) < 5:
            all_error_samples.append(budget.circuit_breaker.last_error[:300])

    secret_val = os.environ.get(api_key_env) if api_key_env else None
    if secret_val:
        all_error_samples = [s.replace(secret_val, "[REDACTED]") for s in all_error_samples]
        if abort_reason:
            abort_reason = abort_reason.replace(secret_val, "[REDACTED]")

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
    budget_calls_used = (
        budget.calls_used
        if (budget.calls_used > 0 or max_calls == 0 or budget.circuit_breaker is not None)
        else usage_calls
    )
    calls = budget_calls_used if (budget.calls_used > 0 or budget.circuit_breaker is not None) else usage_calls
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

    baseline_troops = sum(s["baseline"]["troops"] for s in per_seed)
    exp_troops = sum(s["experiment"]["troops"] for s in per_seed)
    normalized_params = sum(
        s["experiment"]["usage"].get("normalized_params", 0) for s in per_seed
    )

    summary_diagnostics = _aggregate_diagnostics(per_seed, total_exp_turns)
    summary_diagnostics["troops"] = {
        "baseline": baseline_troops,
        "experiment": exp_troops,
    }
    summary_diagnostics["possible_cause_hint"] = generate_possible_cause_hint({
        "diagnostics": summary_diagnostics,
        "orders_accept_rate": orders_accept_rate,
        "baseline_troops": baseline_troops,
        "experiment_troops": exp_troops,
        "per_seed": per_seed,
    })

    if shared_counter is not None and shared_counter.stopped_early:
        budget.stopped_early = True

    summary = {
        "seat": seat,
        "scenario": scenario,
        "seeds": [s["seed"] for s in per_seed],
        "planned_seeds": seed_list,
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
        "normalized_params": normalized_params,
        "diagnostics": summary_diagnostics,
    }

    return {
        "per_seed": per_seed,
        "summary": summary,
        "budget": {
            "max_calls": max_calls,
            "calls_used": budget_calls_used,
            "stopped_early": budget.stopped_early,
        },
        "aborted": aborted,
        "abort_reason": abort_reason,
        "error_samples": all_error_samples,
    }


def render_markdown(result: dict) -> str:
    """Render a Traditional Chinese markdown report from evaluation results."""
    summary = result["summary"]
    budget = result["budget"]
    per_seed = result["per_seed"]
    aborted = result.get("aborted", False)
    abort_reason = result.get("abort_reason")
    error_samples = result.get("error_samples", [])

    lines = []
    if aborted:
        lines.append(f"⚠️ 後端連續失敗，評測已中止：{abort_reason}")
        lines.append("")

    lines.append("# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)")
    lines.append("")
    planned_seeds = summary.get("planned_seeds", summary["seeds"])
    n_planned = len(planned_seeds)
    n_completed = len(summary["seeds"])
    lines.append("## 評測設定")
    lines.append(f"- **評測席位 (Seat)**: `{summary['seat']}`")
    lines.append(f"- **情境 (Scenario)**: `{summary.get('scenario', 'default')}`")
    lines.append(
        f"- **評測種子數**: 計畫種子 {n_planned} 個，實際完成 {n_completed} 個 (種子: `{summary['seeds']}`)"
    )
    lines.append(
        f"- **呼叫預算 (Max Calls)**: {budget['max_calls'] if budget['max_calls'] is not None else '無上限'}"
    )
    calls_status = " (未觸發提前終止)"
    if aborted:
        reason = abort_reason or "後端連續失敗"
        calls_status = f" (已中止（{reason}）)"
    elif budget.get("stopped_early", False):
        calls_status = " (已中止（預算耗盡）)"

    lines.append(f"- **已使用呼叫數 (Calls Used)**: {budget['calls_used']}{calls_status}")
    lines.append("")

    all_llm_failed = (
        (summary["calls"] > 0 and summary["errors"] >= summary["calls"])
        or (summary["calls"] > 0 and summary["plan_failure_rate"] >= 1.0)
    )

    if all_llm_failed:
        lines.append("## 評測摘要（⚠️ 實驗組實為規則 AI 代打，結果無效）")
        lines.append("")
        lines.append("> [!WARNING]")
        lines.append("> 實驗組實為規則 AI 代打，結果無效（全部 LLM 呼叫皆失敗）。")
        lines.append("")
    else:
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
    possible_hint = summary.get("diagnostics", {}).get("possible_cause_hint") or generate_possible_cause_hint(summary)
    lines.append(f"**可能原因提示**：{possible_hint}")
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

    diag = summary.get("diagnostics", {})
    action_counts = diag.get("action_counts", {})
    base_actions = action_counts.get("baseline", {})
    exp_actions = action_counts.get("experiment", {})
    all_action_keys = sorted(set(base_actions.keys()) | set(exp_actions.keys()))

    incidents = diag.get("incidents", {})
    base_inc = incidents.get("baseline", {})
    exp_inc = incidents.get("experiment", {})

    rejection_reasons = diag.get("rejection_reasons", [])
    named_per_turn = diag.get("named_per_turn", {})

    lines.append("## 診斷")
    lines.append("")
    lines.append("### 動作分布 (基準線 vs 實驗組)")
    lines.append("")
    lines.append("| 動作 | 基準線次數 | 實驗組次數 | 差異 |")
    lines.append("| --- | --- | --- | --- |")
    if all_action_keys:
        for act in all_action_keys:
            b_cnt = base_actions.get(act, 0)
            e_cnt = exp_actions.get(act, 0)
            diff = e_cnt - b_cnt
            lines.append(f"| {act} | {b_cnt} | {e_cnt} | {diff:+d} |")
    else:
        lines.append("| (無動作記錄) | 0 | 0 | +0 |")
    lines.append("")

    siege_outcomes = diag.get("siege_outcomes", {})
    base_so = siege_outcomes.get("baseline", {})
    exp_so = siege_outcomes.get("experiment", {})
    b_att = int(base_so.get("attempts", 0))
    e_att = int(exp_so.get("attempts", 0))
    b_cap = int(base_so.get("captured", 0))
    e_cap = int(exp_so.get("captured", 0))
    b_rep = int(base_so.get("repelled", 0))
    e_rep = int(exp_so.get("repelled", 0))

    lines.append("### 攻城勝敗 (出征 / siege_outcomes)")
    lines.append("")
    lines.append("| 指標 | 基準線 | 實驗組 | 差異 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(f"| 攻城嘗試 (siege attempts) | {b_att} | {e_att} | {e_att - b_att:+d} |")
    lines.append(f"| 成功攻克 (captured) | {b_cap} | {e_cap} | {e_cap - b_cap:+d} |")
    lines.append(f"| 擊退受挫 (repelled) | {b_rep} | {e_rep} | {e_rep - b_rep:+d} |")
    lines.append("")

    lines.append("### 出奔 / 抗旨 / 武將流失")
    lines.append("")
    lines.append("| 指標 | 基準線 | 實驗組 | 差異 |")
    lines.append("| --- | --- | --- | --- |")
    b_defect = base_inc.get("deflections", 0)
    e_defect = exp_inc.get("deflections", 0)
    lines.append(f"| 出奔數 | {b_defect} | {e_defect} | {e_defect - b_defect:+d} |")
    b_disobey = base_inc.get("disobeyed", 0)
    e_disobey = exp_inc.get("disobeyed", 0)
    lines.append(f"| 抗旨數 | {b_disobey} | {e_disobey} | {e_disobey - b_disobey:+d} |")
    b_init = base_inc.get("initial_officers", 0)
    e_init = exp_inc.get("initial_officers", 0)
    lines.append(f"| 初始武將數 | {b_init} | {e_init} | {e_init - b_init:+d} |")
    b_fin = base_inc.get("final_officers", 0.0)
    e_fin = exp_inc.get("final_officers", 0.0)
    lines.append(f"| 最終存活武將數 | {b_fin:.1f} | {e_fin:.1f} | {e_fin - b_fin:+.1f} |")
    b_loss = b_init - b_fin
    e_loss = e_init - e_fin
    lines.append(f"| 武將流失數 | {b_loss:.1f} | {e_loss:.1f} | {e_loss - b_loss:+.1f} |")
    b_loyalty = base_inc.get("final_avg_loyalty", 0.0)
    e_loyalty = exp_inc.get("final_avg_loyalty", 0.0)
    lines.append(f"| 最終平均忠誠 | {b_loyalty:.1f} | {e_loyalty:.1f} | {e_loyalty - b_loyalty:+.1f} |")
    lines.append("")

    lines.append("### 被拒指令原因前 3 名")
    lines.append("")
    if rejection_reasons:
        lines.append("| 排名 | 原因 | 次數 |")
        lines.append("| --- | --- | --- |")
        for rank, r_item in enumerate(rejection_reasons, 1):
            r_str = r_item.get("reason", "")
            r_cnt = r_item.get("count", 0)
            lines.append(f"| {rank} | `{r_str}` | {r_cnt} |")
    else:
        lines.append("無指令被拒記錄。")
    lines.append("")

    lines.append("### 點名與委任平均 (每回合)")
    lines.append("")
    lines.append("| 類別 | 平均人數 |")
    lines.append("| --- | --- |")
    named_val = named_per_turn.get("named", 0.0)
    delegated_val = named_per_turn.get("delegated", 0.0)
    lines.append(f"| 點名執行 (Orders) | {named_val:.2f} |")
    lines.append(f"| 系統委任 (Delegated) | {delegated_val:.2f} |")
    lines.append("")

    lines.append("## 預算保護")
    lines.append(f"- **max_calls**: {budget['max_calls']}")
    lines.append(f"- **calls_used**: {budget['calls_used']}")
    lines.append(f"- **stopped_early**: {'是 (True)' if budget['stopped_early'] else '否 (False)'}")
    lines.append("")
    lines.append("## 錯誤樣本")
    lines.append("")
    if error_samples:
        for idx, sample in enumerate(error_samples, 1):
            lines.append(f"{idx}. `{sample}`")
    else:
        lines.append("無錯誤記錄。")
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
    parser = argparse.ArgumentParser(
        description="Run comparative SLG evaluation (LLM vs Rule-based baseline) with call budget protection. Exits with non-zero status code if aborted.",
        epilog="Exit status: 0 on success, 1 if evaluation aborted (e.g. circuit breaker opened), 2 on invalid CLI arguments.",
    )
    parser.add_argument("--seat", type=str, default="faction_2", help="Faction seat to evaluate (default: faction_2)")
    parser.add_argument("--seeds", type=str, default="0-4", help="Seeds range/list, e.g. 0-9 or 1,3,5 (default: 0-4)")
    parser.add_argument("--turns", type=int, default=20, help="Turns per game (default: 20)")
    parser.add_argument("--max-calls", type=int, default=60, help="Maximum LLM call budget (default: 60)")
    parser.add_argument("--baseline-style", type=str, default="balanced", help="Baseline rule-based style (default: balanced)")
    parser.add_argument("--scenario", type=str, default="default", help="Initial state scenario (default: default)")
    parser.add_argument(
        "--extra-body-json",
        type=_parse_extra_body_json,
        default=None,
        help="Additional JSON object to merge into OpenAI request body",
    )
    parser.add_argument("--out", type=str, default=None, help="Output path for markdown report (and .json)")
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
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=None,
        help="Subprocess command for CommandCompleter",
    )

    raw_argv = sys.argv[1:] if argv is None else list(argv)
    known = {
        "--seat",
        "--seeds",
        "--turns",
        "--max-calls",
        "--baseline-style",
        "--scenario",
        "--extra-body-json",
        "--out",
        "--demo",
        "--openai-base-url",
        "--model",
        "--api-key-env",
        "--max-consecutive-errors",
        "--http-retries",
        "--min-interval",
        "--http-timeout",
        "--siege-verdict",
    }
    processed_argv = _reorder_command_args(raw_argv, known)
    args = parser.parse_args(processed_argv)

    completer = build_completer(args)
    if completer is None:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    try:
        seeds = parse_seeds(args.seeds)
    except ValueError as exc:
        print(f"Error parsing seeds: {exc}", file=sys.stderr)
        sys.exit(2)

    agent_factory = lambda budget: LLMFactionAgent(budget.wrap(completer), siege_verdict=args.siege_verdict)

    result = evaluate(
        seeds=seeds,
        turns=args.turns,
        seat=args.seat,
        agent_factory=agent_factory,
        baseline_style=args.baseline_style,
        max_calls=args.max_calls,
        max_consecutive_errors=args.max_consecutive_errors,
        api_key_env=args.api_key_env,
        scenario=args.scenario,
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

    if result.get("aborted", False):
        print(f"⚠️ 評測中止：{result.get('abort_reason', '')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
