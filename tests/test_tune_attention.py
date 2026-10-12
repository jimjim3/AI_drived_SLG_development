"""Tests for the loyalty/neglect constant tuner (slg.sim.tune_attention)."""

import csv
import os
import tempfile
import unittest

import slg.engine.game as game_mod
import slg.engine.view as view_mod
from slg.agents.base import FactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.validation import KNOWN_ACTIONS
from slg.schema import FactionPlan
from slg.sim import tune_attention as ta


class RecordingAgent(FactionAgent):
    """Wraps another FactionAgent and records every plan it issues."""

    def __init__(self, inner):
        self._inner = inner
        self.plans = []

    def decide(self, view):
        plan = self._inner.decide(view)
        self.plans.append(plan)
        return plan


def _combo(nps, npet, lb, db, dbl, plb):
    return dict([
        ("NEGLECT_PENALTY_START", nps),
        ("NEGLECT_PETITION", npet),
        ("LOYALTY_BOOST", lb),
        ("DEFECT_BELOW", db),
        ("DISOBEY_BELOW", dbl),
        ("PETITION_LOYALTY_BELOW", plb),
    ])


class TestTuneAttentionStrategies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state0 = build_initial_state()
        cls.f2_ids = set(ta.faction_officer_ids(cls.state0))

    def _run(self, strategy, seed=0, turns=5):
        agent = RecordingAgent(ta.make_agent(strategy, self.state0, seed,
                                              tuple(sorted(self.f2_ids))))
        agents = dict([
            ("faction_1", RuleBasedAgent("balanced")),
            ("faction_2", agent),
            ("faction_3", RuleBasedAgent("balanced")),
        ])
        import random
        game = Game(self.state0, agents, random.Random(seed))
        game.run(turns)
        return game, agent

    def test_strategies_emit_legal_plans(self):
        # Every plan must only order faction_2 officers with known actions and
        # dict params; next_cast must only reference faction_2 officers.
        for strategy in ("stubborn", "fixed_six", "core8", "random_five", "rotator"):
            game, agent = self._run(strategy, seed=0, turns=5)
            self.assertGreater(len(agent.plans), 0, f"{strategy} issued no plans")
            for plan in agent.plans:
                self.assertIsInstance(plan, FactionPlan)
                for order in plan.orders:
                    self.assertIn(order.officer_id, self.f2_ids,
                                  f"{strategy} ordered non-faction_2 officer")
                    self.assertIn(order.action, KNOWN_ACTIONS,
                                  f"{strategy} ordered unknown action {order.action!r}")
                    self.assertIsInstance(order.params, dict)
                for oid in plan.next_cast:
                    self.assertIn(oid, self.f2_ids,
                                  f"{strategy} requested non-faction_2 officer in next_cast")
            # Engine invariant: every decision is valid (safety net holds).
            self.assertEqual(game.stats["valid"], game.stats["decisions"],
                             f"{strategy} produced invalid decisions")

    def test_random_five_reproducible_same_seed(self):
        def ordered_seq(seed, turns=20):
            agent = RecordingAgent(ta.make_agent("random_five", self.state0, seed,
                                                 tuple(sorted(self.f2_ids))))
            agents = dict([
                ("faction_1", RuleBasedAgent("balanced")),
                ("faction_2", agent),
                ("faction_3", RuleBasedAgent("balanced")),
            ])
            import random
            game = Game(self.state0, agents, random.Random(seed))
            game.run(turns)
            return (
                [tuple(p.ordered) for p in game.faction_logs
                 if p.faction_id == "faction_2"],
                [tuple((i.turn, i.officer_id) for i in game.incidents
                       if i.action == "defect" and i.faction_id == "faction_2")],
            )

        seq_a = ordered_seq(7)
        seq_b = ordered_seq(7)
        self.assertEqual(seq_a, seq_b, "same seed must reproduce the same game")

        seq_c = ordered_seq(8)
        self.assertNotEqual(seq_a[0], seq_c[0],
                            "different seeds must name different officers")


class TestTuneAttentionOverride(unittest.TestCase):
    def test_override_patches_engine_modules_and_restores(self):
        combo = _combo(2, 2, 3, 50, 60, 90)
        with ta.override_constants(combo):
            self.assertEqual(game_mod.NEGLECT_PENALTY_START, 2)
            self.assertEqual(game_mod.DEFECT_BELOW, 50)
            self.assertEqual(game_mod.DISOBEY_BELOW, 60)
            self.assertEqual(game_mod.LOYALTY_BOOST, 3)
            self.assertEqual(view_mod.NEGLECT_PETITION, 2)
            self.assertEqual(view_mod.PETITION_LOYALTY_BELOW, 90)
        # restored to the shipped values
        self.assertEqual(game_mod.NEGLECT_PENALTY_START, ta.BASELINE_CONSTANTS["NEGLECT_PENALTY_START"])
        self.assertEqual(game_mod.DEFECT_BELOW, ta.BASELINE_CONSTANTS["DEFECT_BELOW"])
        self.assertEqual(view_mod.NEGLECT_PETITION, ta.BASELINE_CONSTANTS["NEGLECT_PETITION"])
        self.assertEqual(view_mod.PETITION_LOYALTY_BELOW, ta.BASELINE_CONSTANTS["PETITION_LOYALTY_BELOW"])

    def test_override_changes_defection_counts(self):
        # Two very different constant sets must produce different defection
        # counts (fixed_six, seeds 0-2, 20 turns).  If the override did not
        # reach the engine, both totals would be identical.
        a = _combo(2, 4, 1, 50, 50, 80)
        b = _combo(5, 4, 1, 35, 50, 80)
        stats_a = ta.run_strategy(a, "fixed_six", seeds=(0, 1, 2), turns=20)
        stats_b = ta.run_strategy(b, "fixed_six", seeds=(0, 1, 2), turns=20)
        total_a = stats_a["avg_defects"] * 3
        total_b = stats_b["avg_defects"] * 3
        self.assertNotEqual(total_a, total_b,
                            "constant override must change defection counts")


class TestTuneAttentionGridAndCSV(unittest.TestCase):
    # 2x2 grid: NPS in {2,5} x DEFECT_BELOW in {35,50}, others fixed at
    # NEGLECT_PETITION=4, LOYALTY_BOOST=2, DISOBEY_BELOW=50,
    # PETITION_LOYALTY_BELOW=80.  Known outcome (20 seeds, 40 turns):
    #   (2, 35) passes all acceptance conditions;
    #   (2, 50) fails only random_five_defect_seeds<=30% (measured 35%);
    #   (5, 35) fails only random_five_loyalty<=baseline-4 (measured 92.15);
    #   (5, 50) fails only random_five_loyalty<=baseline-4 (measured 91.96).
    GRID = dict([
        ("NEGLECT_PENALTY_START", (2, 5)),
        ("NEGLECT_PETITION", (4,)),
        ("LOYALTY_BOOST", (2,)),
        ("DEFECT_BELOW", (35, 50)),
        ("DISOBEY_BELOW", (50,)),
        ("PETITION_LOYALTY_BELOW", (80,)),
    ])

    @classmethod
    def setUpClass(cls):
        cls.results = ta.run_grid(cls.GRID, workers=8)

    def test_build_grid_sizes(self):
        self.assertEqual(len(ta.build_grid()), 1296)
        combos = ta.build_grid(self.GRID)
        self.assertEqual(len(combos), 4)
        keys = set(ta.combo_key(c) for c in combos)
        self.assertEqual(
            keys,
            {(2, 4, 2, 35, 50, 80), (2, 4, 2, 50, 50, 80),
             (5, 4, 2, 35, 50, 80), (5, 4, 2, 50, 50, 80)},
        )

    def test_combo_distance(self):
        baseline_combo = dict(zip(ta.TUNABLE, tuple(ta.BASELINE_CONSTANTS.values())))
        self.assertEqual(ta.combo_distance(baseline_combo), 0)
        # Two combos differing in exactly one constant by 1 must differ in
        # distance by exactly 1.
        a = _combo(2, 4, 2, 35, 50, 80)
        b = _combo(2, 3, 2, 35, 50, 80)
        self.assertEqual(abs(ta.combo_distance(a) - ta.combo_distance(b)), 1)
        # Distance is a sum of absolute differences, never negative.
        self.assertGreaterEqual(ta.combo_distance(a), 0)

    def test_csv_fields_and_format(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            ta.write_csv(self.results, path)
            with open(path, newline="") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(rows[0], ta.CSV_COLUMNS)
            body = rows[1:]
            self.assertEqual(len(body), 4 * len(ta.STRATEGIES))
            seen_combos = set()
            for row in body:
                self.assertEqual(len(row), len(ta.CSV_COLUMNS))
                seen_combos.add(tuple(row[:6]))
                strategy = row[6]
                self.assertIn(strategy, ta.STRATEGIES)
                defect_ratio = float(row[7])
                avg_defects = float(row[8])
                early_ratio = float(row[9])
                final_loyalty = float(row[10])
                disobey_total = int(row[11])
                self.assertTrue(0.0 <= defect_ratio <= 1.0)
                self.assertGreaterEqual(avg_defects, 0.0)
                self.assertTrue(0.0 <= early_ratio <= 1.0)
                self.assertTrue(0.0 <= final_loyalty <= 100.0)
                self.assertGreaterEqual(disobey_total, 0)
            self.assertEqual(len(seen_combos), 4)
        finally:
            os.unlink(path)

    def test_small_grid_finds_known_passing_and_failing(self):
        best_key, best_conds, passing_keys = ta.select_combination(self.results)
        self.assertEqual(passing_keys, [(2, 4, 2, 35, 50, 80)])
        self.assertEqual(best_key, (2, 4, 2, 35, 50, 80))
        self.assertTrue(all(ok for _, ok, _ in best_conds))

        # (5, 35): Rotator passes, but the random_five loyalty gap fails.
        conds_535 = dict(
            (name, ok) for name, ok, _ in ta.check_conditions(self.results[(5, 4, 2, 35, 50, 80)])
        )
        self.assertTrue(conds_535["rotator_zero_defect_seeds>=90%"])
        self.assertFalse(conds_535["random_five_loyalty<=baseline-4"])

        # (2, 50): random_five defect seed ratio fails (measured 35% > 30%).
        conds_250 = dict(
            (name, ok) for name, ok, _ in ta.check_conditions(self.results[(2, 4, 2, 50, 50, 80)])
        )
        self.assertFalse(conds_250["random_five_defect_seeds<=30%"])
        self.assertTrue(conds_250["random_five_loyalty<=baseline-4"])


class TestTuneAttentionShippedConstants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One-combo grid pinned to the constants shipped in schema.py.
        grid = dict([(name, (val,)) for name, val in ta.BASELINE_CONSTANTS.items()])
        cls.results = ta.run_grid(grid, workers=8)
        cls.per_strategy = list(cls.results.values())[0]

    def test_baseline_zero_defect_and_disobey(self):
        stats = self.per_strategy["baseline"]
        self.assertEqual(stats["defect_seed_ratio"], 0.0)
        self.assertEqual(stats["disobey_total"], 0)

    def test_shipped_constants_satisfy_all_conditions(self):
        # The constants currently shipped in schema.py must satisfy every
        # Task-M acceptance condition (this is what the behavioral tests in
        # tests/test_attention_behavior.py assert individually).
        conds = ta.check_conditions(self.per_strategy)
        failed = [(name, detail) for name, ok, detail in conds if not ok]
        self.assertEqual(failed, [], f"shipped constants fail: {failed}")


if __name__ == "__main__":
    unittest.main()
