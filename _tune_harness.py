"""Scratch tuning harness (deleted before finishing)."""
import random
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game, compute_winner
from slg.engine.initial_state import build_initial_state


def make_state(cities):
    base = build_initial_state()
    new_cities = {}
    for cid, vals in cities.items():
        c = base.city(cid)
        new_cities[cid] = replace(c, **vals)
    return replace(base, cities=new_cities)


def run_game(state, seed, turns, styles):
    rng = random.Random(seed)
    agents = {fid: RuleBasedAgent(styles[i]) for i, fid in enumerate(sorted(state.factions))}
    game = Game(state, agents, rng)
    final = game.run(turns)
    return final, game


def scan(cities, turns=30, styles=("balanced", "aggressive", "turtle"),
         recruit_target=600, siege_combat=70, ratios=None, seeds=range(40)):
    if ratios:
        RuleBasedAgent.SIEGE_RATIO.update(ratios)
    RuleBasedAgent.RECRUIT_TARGET = recruit_target
    RuleBasedAgent.SIEGE_MIN_COMBAT = siege_combat
    winners = []
    rests = 0
    decisions = 0
    bad = []
    for s in seeds:
        state = make_state(cities)
        final, game = run_game(state, s, turns, styles)
        winners.append(compute_winner(final))
        acts = [e.action for e in game.log_entries]
        rests += acts.count("rest")
        decisions += len(acts)
        st = game.stats
        if not (st["valid"] == st["decisions"] and st["fallbacks"] == 0):
            bad.append(s)
    c = Counter(winners)
    print("winners:", dict(c))
    print("rest: %d/%d = %.3f" % (rests, decisions, rests / max(decisions, 1)))
    print("bad seeds:", bad)
    for f in ("faction_1", "faction_2", "faction_3"):
        print(f, "wins:", c.get(f, 0))
    return c


if __name__ == "__main__":
    scan({})
