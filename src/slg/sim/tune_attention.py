"""Grid-search tuner for the loyalty / neglect constants (Task M).

Background (docs/EVALUATION.md section 9): with the original constants, a
real LLM player (Qwen3.8-27B) naming ~4.5 of 14 officers per turn produced
0 defections and 0 disobey incidents over 40 turns.  The neglect thresholds
were too lax for actual play.  This tool grid-searches the tunable
constants (``slg.schema``) against deterministic test strategies at the
``faction_2`` seat and reports which combinations make the mechanics "have
teeth" while keeping a rotating-attention player safe.

Usage::

    PYTHONPATH=src python3 -m slg.sim.tune_attention --csv out.csv
    PYTHONPATH=src python3 -m slg.sim.tune_attention \
        --neglect-penalty-start 2,5 --defect-below 35,50 --csv small.csv

Only the constants listed in :data:`TUNABLE` are touched; the engine logic
is never modified.  Because ``slg.engine.game`` and ``slg.engine.view``
bind the constants at import time (``from ..schema import X``), an override
patches the module attributes of those two modules (plus ``slg.schema``
itself) and restores them afterwards.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import multiprocessing as mp
import os
import random
from contextlib import contextmanager
from typing import Mapping, Sequence

from .. import schema as _schema_mod
from ..agents.backends import _parse_legal_str
from ..agents.base import FactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..engine import game as _game_mod
from ..engine import view as _view_mod
from ..engine.initial_state import build_initial_state
from ..schema import AgentDecision, FactionPlan
from .headless import run_headless

# --- fixed experimental setup ----------------------------------------------

FACTION_ID = "faction_2"
SEEDS = tuple(range(20))
TURNS = 40
EARLY_TURNS = 8
EARLY_MAX_FRACTION = 0.25

TUNABLE = (
    "NEGLECT_PENALTY_START",
    "NEGLECT_PETITION",
    "LOYALTY_BOOST",
    "DEFECT_BELOW",
    "DISOBEY_BELOW",
    "PETITION_LOYALTY_BELOW",
)

DEFAULT_GRID: dict[str, tuple[int, ...]] = {
    "NEGLECT_PENALTY_START": (2, 3, 4, 5),
    "NEGLECT_PETITION": (2, 3, 4),
    "LOYALTY_BOOST": (1, 2, 3),
    "DEFECT_BELOW": (35, 40, 45, 50),
    "DISOBEY_BELOW": (50, 55, 60),
    "PETITION_LOYALTY_BELOW": (80, 85, 90),
}

# Reference point for the "distance from current constants" ranking: the
# values shipped in schema.py at import time (before any override applies).
BASELINE_CONSTANTS: dict[str, int] = {
    name: int(getattr(_schema_mod, name)) for name in TUNABLE
}

# Modules that bind each constant at import time and therefore must be
# patched for an override to take effect in the engine.
_OVERRIDE_TARGETS: dict[str, tuple] = {
    "NEGLECT_PENALTY_START": (_game_mod, _schema_mod),
    "NEGLECT_PETITION": (_view_mod, _schema_mod),
    "LOYALTY_BOOST": (_game_mod, _schema_mod),
    "DEFECT_BELOW": (_game_mod, _schema_mod),
    "DISOBEY_BELOW": (_game_mod, _schema_mod),
    "PETITION_LOYALTY_BELOW": (_view_mod, _schema_mod),
}

STRATEGIES = ("stubborn", "fixed_six", "core8", "random_five", "rotator", "baseline")


# --- constant override -------------------------------------------------------

def set_constants(combo: Mapping[str, int]) -> None:
    """Patch the tunable constants into every module that binds them."""
    for name in TUNABLE:
        for mod in _OVERRIDE_TARGETS[name]:
            setattr(mod, name, int(combo[name]))


@contextmanager
def override_constants(combo: Mapping[str, int]):
    """Temporarily apply ``combo`` to the engine modules; restore on exit."""
    saved = []
    for name in TUNABLE:
        for mod in _OVERRIDE_TARGETS[name]:
            saved.append((mod, name, getattr(mod, name)))
    set_constants(combo)
    try:
        yield
    finally:
        for mod, name, value in saved:
            setattr(mod, name, value)


# --- test strategies (faction_2 seat; input is the FactionView only) ---------

def _first_non_rest_order(c: dict) -> AgentDecision | None:
    """First non-rest legal action of a cast entry, as an AgentDecision."""
    for legal_str in c["legal"]:
        act, params = _parse_legal_str(legal_str)
        if act != "rest":
            return AgentDecision(c["id"], act, params)
    return None


class StubbornAgent(FactionAgent):
    """Never issues orders; every officer is delegated to the rule agent."""

    def decide(self, view):
        return FactionPlan(orders=())


class FixedSixAgent(FactionAgent):
    """Always orders the same six officers: the first six of the turn-1 cast."""

    def __init__(self):
        self._fixed_six: tuple[str, ...] | None = None

    def decide(self, view):
        if self._fixed_six is None:
            self._fixed_six = tuple(c["id"] for c in view.cast[:6])
        cast_by_id = {c["id"]: c for c in view.cast}
        orders = []
        for oid in self._fixed_six:
            c = cast_by_id.get(oid)
            if c is None:
                continue
            d = _first_non_rest_order(c)
            if d is not None:
                orders.append(d)
        return FactionPlan(orders=tuple(orders), next_cast=self._fixed_six)


class Core8Agent(FactionAgent):
    """Always orders a fixed "core" of the 8 strongest officers of the faction
    (ranked by politics+war+leadership, then officer_id).  Only the first six
    ordered officers are noticed by the engine, so 8 officers are never
    noticed at all."""

    def __init__(self, state, faction_id: str = FACTION_ID):
        officers = [o for o in state.officers.values() if o.faction_id == faction_id]
        officers.sort(key=lambda o: (-(o.politics + o.war + o.leadership), o.officer_id))
        self._core8 = tuple(o.officer_id for o in officers[:8])

    def decide(self, view):
        cast_by_id = {c["id"]: c for c in view.cast}
        orders = []
        for oid in self._core8:
            c = cast_by_id.get(oid)
            if c is None:
                continue
            d = _first_non_rest_order(c)
            if d is not None:
                orders.append(d)
        return FactionPlan(orders=tuple(orders), next_cast=self._core8)


class RandomFiveAgent(FactionAgent):
    """Names 5 random officers per turn: ``random.Random(seed*1000+turn)``
    samples 5 of the faction's officers.  The current turn's five are ordered
    (when visible in the cast); the next turn's five are requested via
    ``next_cast`` so that they are visible when they get named."""

    def __init__(self, seed: int, officer_ids: Sequence[str]):
        self._seed = seed
        self._officer_ids = tuple(officer_ids)

    def _sample(self, turn: int) -> tuple[str, ...]:
        return tuple(
            random.Random(self._seed * 1000 + turn).sample(list(self._officer_ids), 5)
        )

    def decide(self, view):
        cast_by_id = {c["id"]: c for c in view.cast}
        orders = []
        for oid in self._sample(view.turn):
            c = cast_by_id.get(oid)
            if c is None:
                continue
            d = _first_non_rest_order(c)
            if d is not None:
                orders.append(d)
        return FactionPlan(orders=tuple(orders), next_cast=self._sample(view.turn + 1))


class RotatorAgent(FactionAgent):
    """Orders the six most neglected cast officers; rotates ``next_cast``
    through the whole officer list (six at a time) so that every officer is
    seen in turn."""

    def __init__(self, officer_ids: Sequence[str]):
        self._officer_ids = tuple(officer_ids)
        self._idx = 0

    def decide(self, view):
        n = len(self._officer_ids)
        next_cast = tuple(self._officer_ids[(self._idx + i) % n] for i in range(6))
        self._idx = (self._idx + 6) % n
        sorted_cast = sorted(view.cast, key=lambda c: -c.get("neglect", 0))
        orders = []
        for c in sorted_cast[:6]:
            d = _first_non_rest_order(c)
            if d is not None:
                orders.append(d)
        return FactionPlan(orders=tuple(orders), next_cast=next_cast)


# --- single-run and aggregate statistics -------------------------------------

def faction_officer_ids(state, faction_id: str = FACTION_ID) -> tuple[str, ...]:
    return tuple(
        o.officer_id for o in state.officers.values() if o.faction_id == faction_id
    )


def make_agent(strategy: str, state0, seed: int, officer_ids: tuple[str, ...]):
    if strategy == "stubborn":
        return StubbornAgent()
    if strategy == "fixed_six":
        return FixedSixAgent()
    if strategy == "core8":
        return Core8Agent(state0)
    if strategy == "random_five":
        return RandomFiveAgent(seed, officer_ids)
    if strategy == "rotator":
        return RotatorAgent(officer_ids)
    raise ValueError(f"unknown strategy {strategy!r}")


def run_single(strategy: str, seed: int, turns: int) -> dict:
    """Run one (strategy, seed) game at the faction_2 seat; return raw stats."""
    state0 = build_initial_state()
    officer_ids = faction_officer_ids(state0)
    if strategy == "baseline":
        agents = {fid: RuleBasedAgent("balanced") for fid in state0.factions}
    else:
        agents = dict(
            [
                ("faction_1", RuleBasedAgent("balanced")),
                ("faction_2", make_agent(strategy, state0, seed, officer_ids)),
                ("faction_3", RuleBasedAgent("balanced")),
            ]
        )
    res = run_headless(seed=seed, turns=turns, agents_by_faction=agents)
    defects = [
        inc for inc in res.incidents
        if inc.action == "defect" and inc.faction_id == FACTION_ID
    ]
    early = [inc for inc in defects if inc.turn <= EARLY_TURNS]
    final_loyalties = [res.final_state.officers[oid].loyalty for oid in officer_ids]
    return {
        "defects": len(defects),
        "early_defects": len(early),
        "disobey": res.stats.get("disobeyed", 0),
        "final_avg_loyalty": sum(final_loyalties) / len(final_loyalties),
    }


def run_strategy(
    combo: Mapping[str, int] | None,
    strategy: str,
    seeds: Sequence[int] = SEEDS,
    turns: int = TURNS,
) -> dict:
    """Aggregate one strategy over ``seeds`` under constants ``combo``.

    ``combo=None`` runs with whatever constants the engine modules currently
    hold (normally the values shipped in schema.py).
    """
    if combo is not None:
        with override_constants(combo):
            per_seed = [run_single(strategy, seed, turns) for seed in seeds]
    else:
        per_seed = [run_single(strategy, seed, turns) for seed in seeds]
    n = len(per_seed)
    n_officers = len(faction_officer_ids(build_initial_state()))
    max_early = max(p["early_defects"] for p in per_seed)
    return {
        "defect_seed_ratio": sum(1 for p in per_seed if p["defects"] > 0) / n,
        "zero_defect_seed_ratio": sum(1 for p in per_seed if p["defects"] == 0) / n,
        "avg_defects": sum(p["defects"] for p in per_seed) / n,
        "max_early_defects": max_early,
        "max_early_defect_ratio": max_early / n_officers,
        "final_avg_loyalty": sum(p["final_avg_loyalty"] for p in per_seed) / n,
        "disobey_total": sum(p["disobey"] for p in per_seed),
    }


# --- acceptance conditions (Task M, 20 seeds / 40 turns, faction_2 seat) -----

def check_conditions(per_strategy: Mapping[str, dict], n_officers: int = 14):
    """Return [(name, passed, detail)] for the Task-M acceptance conditions."""
    conds = []
    rot = per_strategy["rotator"]
    conds.append((
        "rotator_zero_defect_seeds>=90%",
        rot["zero_defect_seed_ratio"] >= 0.90,
        f"{rot['zero_defect_seed_ratio']:.0%}",
    ))
    rf = per_strategy["random_five"]
    bl = per_strategy["baseline"]
    conds.append((
        "random_five_defect_seeds<=30%",
        rf["defect_seed_ratio"] <= 0.30,
        f"{rf['defect_seed_ratio']:.0%}",
    ))
    conds.append((
        "random_five_loyalty<=baseline-4",
        rf["final_avg_loyalty"] <= bl["final_avg_loyalty"] - 4.0,
        f"{rf['final_avg_loyalty']:.2f} vs baseline {bl['final_avg_loyalty']:.2f}",
    ))
    c8 = per_strategy["core8"]
    conds.append((
        "core8_defect_seeds>=50%",
        c8["defect_seed_ratio"] >= 0.50,
        f"{c8['defect_seed_ratio']:.0%}",
    ))
    fs = per_strategy["fixed_six"]
    conds.append((
        "fixed_six_defect_seeds>=90%",
        fs["defect_seed_ratio"] >= 0.90,
        f"{fs['defect_seed_ratio']:.0%}",
    ))
    st = per_strategy["stubborn"]
    conds.append((
        "stubborn_defect_seeds>=90%",
        st["defect_seed_ratio"] >= 0.90,
        f"{st['defect_seed_ratio']:.0%}",
    ))
    conds.append((
        "stubborn_early<=25%_officers",
        st["max_early_defects"] <= n_officers * EARLY_MAX_FRACTION,
        f"max {st['max_early_defects']} early <= {n_officers * EARLY_MAX_FRACTION:g}",
    ))
    conds.append((
        "baseline_zero_defect_disobey",
        bl["defect_seed_ratio"] == 0.0 and bl["disobey_total"] == 0,
        f"defect seeds {bl['defect_seed_ratio']:.0%}, disobey {bl['disobey_total']}",
    ))
    return conds


# --- grid, selection, CSV ------------------------------------------------------

def build_grid(grid: Mapping[str, Sequence[int]] | None = None) -> list[dict]:
    grid = grid if grid is not None else DEFAULT_GRID
    keys = [k for k in TUNABLE if k in grid]
    combos = []
    for values in itertools.product(*(sorted(grid[k]) for k in keys)):
        combos.append(dict(zip(keys, values)))
    return combos


def combo_key(combo: Mapping[str, int]) -> tuple:
    return tuple(int(combo[name]) for name in TUNABLE)


def combo_distance(combo: Mapping[str, int]) -> int:
    """Sum of absolute differences from the constants shipped in schema.py."""
    return sum(abs(int(combo[name]) - BASELINE_CONSTANTS[name]) for name in TUNABLE)


def select_combination(results: Mapping[tuple, Mapping[str, dict]]):
    """Pick the best combination.

    Returns ``(combo_key, conditions, passing_keys)`` where ``passing_keys``
    is the list of keys satisfying all conditions sorted by distance (empty
    when nothing passes; the fallback is then the combination with the fewest
    violations, the Rotator condition required to pass, then distance).
    """
    evaluated = []
    for key, per_strategy in results.items():
        conds = check_conditions(per_strategy)
        violations = [c for c in conds if not c[1]]
        rot_ok = conds[0][1]
        evaluated.append((key, conds, violations, rot_ok))

    passing = [e for e in evaluated if not e[2]]
    if passing:
        passing.sort(key=lambda e: (combo_distance(dict(zip(TUNABLE, e[0]))), e[0]))
        return passing[0][0], passing[0][1], [e[0] for e in passing]

    candidates = [e for e in evaluated if e[3]]
    pool = candidates if candidates else evaluated
    pool.sort(key=lambda e: (len(e[2]), combo_distance(dict(zip(TUNABLE, e[0]))), e[0]))
    best = pool[0]
    return best[0], best[1], []


CSV_COLUMNS = [
    "neglect_penalty_start", "neglect_petition", "loyalty_boost",
    "defect_below", "disobey_below", "petition_loyalty_below",
    "strategy",
    "defect_seed_ratio", "avg_defects", "max_early_defect_ratio",
    "final_avg_loyalty", "disobey_total",
]


def write_csv(results: Mapping[tuple, Mapping[str, dict]], path: str) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for key in sorted(results):
            combo = dict(zip(TUNABLE, key))
            for strategy in STRATEGIES:
                st = results[key].get(strategy)
                if st is None:
                    continue
                w.writerow([
                    combo["NEGLECT_PENALTY_START"],
                    combo["NEGLECT_PETITION"],
                    combo["LOYALTY_BOOST"],
                    combo["DEFECT_BELOW"],
                    combo["DISOBEY_BELOW"],
                    combo["PETITION_LOYALTY_BELOW"],
                    strategy,
                    f"{st['defect_seed_ratio']:.4f}",
                    f"{st['avg_defects']:.4f}",
                    f"{st['max_early_defect_ratio']:.4f}",
                    f"{st['final_avg_loyalty']:.4f}",
                    st["disobey_total"],
                ])


# --- parallel driver -----------------------------------------------------------

def _worker(task):
    combo, strategy, seeds, turns = task
    set_constants(combo)
    stats = run_strategy(None, strategy, seeds=seeds, turns=turns)
    return combo_key(combo), strategy, stats


def run_grid(
    grid: Mapping[str, Sequence[int]] | None = None,
    seeds: Sequence[int] = SEEDS,
    turns: int = TURNS,
    strategies: Sequence[str] = STRATEGIES,
    workers: int = 1,
    progress=None,
) -> dict:
    """Run every (combo, strategy) pair; return {combo_key: {strategy: stats}}."""
    combos = build_grid(grid)
    tasks = [(combo, s, tuple(seeds), turns) for combo in combos for s in strategies]
    results: dict[tuple, dict] = {combo_key(c): {} for c in combos}
    done = 0
    total = len(tasks)

    def _record(key, strategy, stats):
        results[key][strategy] = stats
        nonlocal done
        done += 1
        if progress is not None and (done % 200 == 0 or done == total):
            progress(done, total)

    if workers > 1 and total > 1:
        ctx = mp.get_context("fork")
        with ctx.Pool(workers) as pool:
            for key, strategy, stats in pool.imap_unordered(_worker, tasks, chunksize=4):
                _record(key, strategy, stats)
    else:
        for task in tasks:
            key, strategy, stats = _worker(task)
            _record(key, strategy, stats)
    return results


def _fmt_combo(key: tuple) -> str:
    return " ".join(f"{n}={v}" for n, v in zip(TUNABLE, key))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Grid-search the loyalty/neglect constants (Task M)."
    )
    parser.add_argument("--csv", default="tune_attention_results.csv",
                        help="output CSV path (default: tune_attention_results.csv)")
    parser.add_argument("--turns", type=int, default=TURNS)
    parser.add_argument("--seed-start", type=int, default=SEEDS[0])
    parser.add_argument("--seed-count", type=int, default=len(SEEDS))
    parser.add_argument("--workers", type=int, default=min(32, os.cpu_count() or 1))
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    for name in TUNABLE:
        parser.add_argument(
            "--" + name.lower().replace("_", "-"),
            default=None,
            help=f"comma-separated grid values for {name}",
        )
    args = parser.parse_args(argv)

    grid = {}
    for name in TUNABLE:
        raw = getattr(args, name.lower())  # argparse dest uses underscores
        grid[name] = (
            tuple(int(v) for v in raw.split(",")) if raw else DEFAULT_GRID[name]
        )

    seeds = tuple(range(args.seed_start, args.seed_start + args.seed_count))
    strategies = tuple(s.strip() for s in args.strategies.split(",") if s.strip())
    n_combos = len(build_grid(grid))
    print(f"grid: {n_combos} combinations x {len(strategies)} strategies x "
          f"{len(seeds)} seeds x {args.turns} turns "
          f"(seeds {seeds[0]}-{seeds[-1]})")

    def _progress(done, total):
        print(f"  ... {done}/{total} (combo, strategy) runs finished")

    results = run_grid(
        grid, seeds=seeds, turns=args.turns, strategies=strategies,
        workers=args.workers, progress=_progress,
    )

    write_csv(results, args.csv)
    print(f"CSV written to {args.csv}")

    # Evaluate acceptance conditions per combination.
    evaluated = []
    for key, per_strategy in results.items():
        conds = check_conditions(per_strategy)
        violations = [c for c in conds if not c[1]]
        evaluated.append((key, conds, violations))

    passing = [e for e in evaluated if not e[2]]
    passing.sort(key=lambda e: (combo_distance(dict(zip(TUNABLE, e[0]))), e[0]))

    print()
    print(f"combinations satisfying ALL acceptance conditions: {len(passing)} "
          f"(sorted by distance from current constants "
          f"{_fmt_combo(tuple(BASELINE_CONSTANTS[n] for n in TUNABLE))})")
    for key, conds, _ in passing[:20]:
        print(f"  d={combo_distance(dict(zip(TUNABLE, key))):>3}  {_fmt_combo(key)}")
    if len(passing) > 20:
        print(f"  ... and {len(passing) - 20} more (see CSV)")

    best_key, best_conds, _ = select_combination(results)
    best_combo = dict(zip(TUNABLE, best_key))
    print()
    if passing:
        print(f"SELECTED combination (all conditions pass, minimal distance): "
              f"{_fmt_combo(best_key)}")
    else:
        print("NO combination satisfies all conditions; fallback selection "
              "(fewest violations, Rotator condition required to pass): "
              f"{_fmt_combo(best_key)}")
        for name, ok, detail in best_conds:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name}: {detail}")

    print()
    print("Selected combination, measured under the six strategies:")
    header = (f"  {'strategy':<12} {'defect_seeds':>13} {'avg_defects':>12} "
              f"{'max_early':>10} {'final_loyalty':>14} {'disobey':>8}")
    print(header)
    for strategy in strategies:
        st = results[best_key].get(strategy)
        if st is None:
            continue
        print(
            f"  {strategy:<12} {st['defect_seed_ratio']:>13.0%} "
            f"{st['avg_defects']:>12.2f} {st['max_early_defects']:>10d} "
            f"{st['final_avg_loyalty']:>14.2f} {st['disobey_total']:>8d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
