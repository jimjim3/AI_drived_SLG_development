"""Behavioral acceptance tests for the tuned loyalty/neglect mechanics (Task M).

Thresholds follow the Task-M spec (20 seeds, 40 turns, faction_2 seat):
  - Rotator:    >= 90% of the seeds have ZERO defections.
  - RandomFive: <= 30% of the seeds have any defection, and the final
                average loyalty is at least 4 points below the rule-AI
                baseline.
  - Core8:      >= 50% of the seeds have at least 1 defection.
  - FixedSix:   >= 90% of the seeds have at least 1 defection.
  - Stubborn:   >= 90% of the seeds have at least 1 defection, and within
                the first 8 turns no seed has more defections than 25% of
                the faction's officers.
  - Baseline:   zero defections and zero disobey.

The strategies themselves live in ``slg.sim.tune_attention`` (single source
of truth shared with the tuning tool).
"""

import unittest

from slg.engine.initial_state import build_initial_state
from slg.sim.tune_attention import SEEDS, TURNS, faction_officer_ids, run_strategy

STRATEGY_NAMES = ("stubborn", "fixed_six", "core8", "random_five", "rotator", "baseline")


class TestAttentionBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n_officers = len(faction_officer_ids(build_initial_state()))
        cls.stats = {
            name: run_strategy(None, name, seeds=SEEDS, turns=TURNS)
            for name in STRATEGY_NAMES
        }

    def test_rotator_zero_defection(self):
        # Rotator: >= 90% of seeds 0-19 within 40 turns have ZERO defections.
        ratio = self.stats["rotator"]["zero_defect_seed_ratio"]
        self.assertGreaterEqual(
            ratio,
            0.90,
            f"Rotator zero-defection ratio {ratio:.1%} should be >= 90%",
        )

    def test_random_five_defect_ratio_bounded(self):
        # RandomFive: <= 30% of seeds 0-19 within 40 turns have any defection.
        ratio = self.stats["random_five"]["defect_seed_ratio"]
        self.assertLessEqual(
            ratio,
            0.30,
            f"RandomFive defection seed ratio {ratio:.1%} should be <= 30%",
        )

    def test_random_five_loyalty_below_baseline(self):
        # RandomFive: final average loyalty at least 4 points below the
        # rule-AI baseline (the neglect must be "felt").
        rf = self.stats["random_five"]["final_avg_loyalty"]
        bl = self.stats["baseline"]["final_avg_loyalty"]
        self.assertLessEqual(
            rf,
            bl - 4.0,
            f"RandomFive final loyalty {rf:.2f} should be <= baseline "
            f"{bl:.2f} - 4 = {bl - 4.0:.2f}",
        )

    def test_core8_defection(self):
        # Core8: >= 50% of seeds 0-19 within 40 turns have at least 1 defection.
        ratio = self.stats["core8"]["defect_seed_ratio"]
        self.assertGreaterEqual(
            ratio,
            0.50,
            f"Core8 defection seed ratio {ratio:.1%} should be >= 50%",
        )

    def test_fixed_six_defection(self):
        # FixedSix: >= 90% of seeds 0-19 within 40 turns have at least 1 defection.
        ratio = self.stats["fixed_six"]["defect_seed_ratio"]
        self.assertGreaterEqual(
            ratio,
            0.90,
            f"FixedSix defection seed ratio {ratio:.1%} should be >= 90%",
        )

    def test_stubborn_defection(self):
        # Stubborn: >= 90% of seeds 0-19 within 40 turns have at least 1 defection.
        ratio = self.stats["stubborn"]["defect_seed_ratio"]
        self.assertGreaterEqual(
            ratio,
            0.90,
            f"Stubborn defection seed ratio {ratio:.1%} should be >= 90%",
        )

    def test_stubborn_early_defection_capped(self):
        # Stubborn: within the first 8 turns, defections in any seed are at
        # most 25% of the faction's officers.
        max_early = self.stats["stubborn"]["max_early_defects"]
        cap = self.n_officers * 0.25
        self.assertLessEqual(
            max_early,
            cap,
            f"Early defection max {max_early} exceeds 25% of officers ({cap:g})",
        )

    def test_rule_based_baseline_zero(self):
        # All balanced rule-based agents: zero defect and zero disobey across
        # all seeds 0-19 within 40 turns.
        bl = self.stats["baseline"]
        self.assertEqual(
            bl["defect_seed_ratio"], 0.0,
            f"Baseline had defections in {bl['defect_seed_ratio']:.1%} of seeds",
        )
        self.assertEqual(
            bl["disobey_total"], 0,
            f"Baseline had {bl['disobey_total']} disobey incidents",
        )


if __name__ == "__main__":
    unittest.main()
