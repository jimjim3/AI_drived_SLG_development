import importlib.util
import pathlib
import unittest

from slg.engine.initial_state import build_initial_state

_spec = importlib.util.spec_from_file_location(
    "attack_opportunities", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "attack_opportunities.py")
ao = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ao)


class AttackOpportunitiesTest(unittest.TestCase):
    def test_best_ratio_matches_the_siege_verdict_inputs(self):
        # at the start nobody has a favourable attack (this is the balance finding recorded in EVALUATION.md §13)
        state = build_initial_state("default")
        for f in ao.FACTIONS:
            self.assertLess(ao.best_ratio(state, f), 1.0)

    def test_favoured_faction_in_the_attack_scenario_has_a_better_ratio(self):
        default = ao.best_ratio(build_initial_state("default"), "faction_2")
        boosted = ao.best_ratio(build_initial_state("advantage"), "faction_2")
        self.assertGreater(boosted, default)
        self.assertGreater(boosted, 1.3)

    def test_collect_shape(self):
        rows = ao.collect("default", seeds=1, turns=2)
        self.assertEqual({k: len(v) for k, v in rows.items()}, {f: 2 for f in ao.FACTIONS})


if __name__ == "__main__":
    unittest.main()
