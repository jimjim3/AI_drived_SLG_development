import copy
import json
import unittest
from pathlib import Path

from slg.engine import scenario
from slg.engine.initial_state import build_initial_state
from slg.sim.headless import run_headless

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "data" / "scenarios" / "default_v1.json"


def doc():
    return json.loads(DEFAULT.read_text(encoding="utf-8"))


class ScenarioTest(unittest.TestCase):
    def test_default_v1_is_valid(self):
        self.assertEqual(scenario.validate(doc()), [])

    def test_loading_default_v1_matches_builtin_state(self):
        state, meta = scenario.load(DEFAULT)
        ref = build_initial_state("default")
        self.assertEqual(state.cities, ref.cities)
        self.assertEqual(state.officers, ref.officers)
        self.assertEqual(state.factions, ref.factions)
        self.assertEqual({k: set(v) for k, v in state.adjacency.items()}, {k: set(v) for k, v in ref.adjacency.items()})
        self.assertEqual(meta.victory, {"type": "most_cities", "turns": 30})
        self.assertEqual(meta.capitals["faction_2"], "luoyang")
        self.assertEqual(set(meta.playable), {"faction_1", "faction_2", "faction_3"})

    def test_loaded_scenario_plays_like_the_builtin_one(self):
        # neighbor order differs (sorted vs hand-written), so this also guards against order-dependent behavior
        from slg.engine.game import Game, compute_winner
        from slg.agents.rule_based import RuleBasedAgent
        import random

        def play(state):
            g = Game(state, {f: RuleBasedAgent("balanced") for f in sorted(state.factions)}, random.Random(5))
            for _ in range(12):
                g.step()
            return compute_winner(g.state), {c: (x.owner, x.troops) for c, x in g.state.cities.items()}

        a = play(scenario.load(DEFAULT)[0])
        b = play(build_initial_state("default"))
        self.assertEqual(a, b)

    def _bad(self, mutate, needle):
        d = copy.deepcopy(doc())
        mutate(d)
        problems = scenario.validate(d)
        self.assertTrue(any(needle in x for x in problems), (needle, problems))
        with self.assertRaises(scenario.ScenarioError):
            scenario.build(d)

    def test_rejects_bad_documents(self):
        self._bad(lambda d: d.update(format=2), "unsupported format")
        self._bad(lambda d: d["map"]["edges"].append(["hanzhong", "nowhere"]), "known cities")
        self._bad(lambda d: d["map"]["cities"].append({"id": "island", "name_zh": "孤島", "pos": [0, 0]}), "not connected")
        self._bad(lambda d: d["cities"][0].update(owner="faction_9"), "unknown owner")
        self._bad(lambda d: d["cities"][0].update(owner=None), "neutral")
        self._bad(lambda d: d["cities"][0].update(troops=-5), "troops")
        self._bad(lambda d: d["officers"][0].update(war=101), "war")
        self._bad(lambda d: d["officers"][0].update(city="hanzhong"), "not owned")
        self._bad(lambda d: d["officers"].append(dict(d["officers"][0])), "duplicate officer")
        self._bad(lambda d: d["factions"][0].update(capital="hanzhong"), "capital")
        self._bad(lambda d: d["victory"].update(type="unify"), "victory.type")
        self._bad(lambda d: d.update(rules="no_such_rules"), "ruleset")
        self._bad(lambda d: d["events"].append({"id": "e1", "turn": 0, "text_zh": "x"}), "turn")

    def test_rejects_non_object_and_reports_all_problems(self):
        self.assertTrue(scenario.validate([]))
        d = doc()
        d["officers"][0]["war"] = 200
        d["cities"][1]["troops"] = -1
        self.assertGreaterEqual(len(scenario.validate(d)), 2)

    def test_defaults_for_loyalty_and_ambition(self):
        d = doc()
        for o in d["officers"]:
            o.pop("loyalty"), o.pop("ambition")
        state, _ = scenario.build(d)
        o = next(iter(state.officers.values()))
        self.assertEqual((o.loyalty, o.ambition), (80, 50))


if __name__ == "__main__":
    unittest.main()
