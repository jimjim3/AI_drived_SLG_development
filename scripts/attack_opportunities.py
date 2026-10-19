#!/usr/bin/env python3
"""How often does a favourable siege exist? Offline (rule-AI games, no LLM needed).

For every faction-turn, take the best scouting ratio any officer could get against an adjacent enemy city
when sending the maximum legal troops, then report how often it reaches 1.0 / 1.3 (the siege-verdict
thresholds). Run it before/after a combat-balance change to see whether attacking became viable.

  PYTHONPATH=src python3 scripts/attack_opportunities.py [--seeds 4] [--turns 20] [--scenario default] [--rules v2|soft|softer|softest]
"""
import argparse
import random
import statistics

from slg.agents.rule_based import RuleBasedAgent
from slg.engine.combat import RULESETS, set_rules
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import estimate_siege_ratio

FACTIONS = ("faction_1", "faction_2", "faction_3")


def best_ratio(state, faction_id: str) -> float:
    best = 0.0
    for o in state.officers.values():
        if o.faction_id != faction_id or not o.is_alive:
            continue
        for la in generate_legal_actions(state, o):
            if la.action != "siege":
                continue
            max_troops = int(la.params["troops"].max)
            for target in (la.params["to"].choices or ()):
                r = estimate_siege_ratio(state, o, target, max_troops)
                best = max(best, 99.0 if r == float("inf") else r)
    return best


def collect(scenario: str, seeds: int, turns: int) -> dict[str, list[float]]:
    rows = {f: [] for f in FACTIONS}
    for seed in range(seeds):
        game = Game(build_initial_state(scenario), {f: RuleBasedAgent("balanced") for f in FACTIONS}, random.Random(seed))
        for _ in range(turns):
            for f in FACTIONS:
                rows[f].append(best_ratio(game.state, f))
            game.step()
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--scenario", default="default")
    ap.add_argument("--rules", default="v2", choices=sorted(RULESETS), help="experimental combat rule set")
    a = ap.parse_args()
    set_rules(a.rules)
    for f, v in collect(a.scenario, a.seeds, a.turns).items():
        v = sorted(v)
        print(f"{f}: median {statistics.median(v):.2f}, p90 {v[int(len(v) * 0.9)]:.2f}, max {v[-1]:.2f}, "
              f"turns with ratio>=1.3: {sum(x >= 1.3 for x in v)}/{len(v)}, >=1.0: {sum(x >= 1.0 for x in v)}/{len(v)}")


if __name__ == "__main__":
    main()
