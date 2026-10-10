"""Empirical balance regression tests for rules v2.

Thresholds are established from empirical measurements on 2026-10-10 (Task E scenario expansion):
- Sweeping seeds 0-39 with turns=30 produces winner distribution:
    faction_1: 12 wins, faction_2: 12 wins, faction_3: 12 wins, draw (None): 4.
- Rest action ratio across all decisions: ~0.4746 (23,922 / 50,400).
- Safety net fallback count: 0 (100% of decisions valid on primary attempt).
- World state variety: 40 unique final (city owner, city troops) configurations.
"""

from collections import Counter
from pathlib import Path
import sys
from typing import Sequence
import unittest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from slg.sim.headless import GameResult, run_headless


class BalanceTests(unittest.TestCase):
    """Empirical balance tests over seeds 0-39 (30 turns).

    As noted in the 2026-10-10 (Task E calibration), the 30-turn simulation
    over seeds 0-39 yields:
      - Winner counts: faction_1: 12, faction_2: 12, faction_3: 12, None: 4 (all 3 factions win >= 3 times).
      - faction_1 win share is bounded under 0.70 (0.300 actual).
      - rest action ratio is bounded under 0.75 (~0.475 actual).
      - stats['valid'] == stats['decisions'] and stats['fallbacks'] == 0 for all games.
      - At least 5 distinct final state configurations are reached (40 actual).
    """

    _cached_results: list[GameResult] | None = None

    @classmethod
    def setUpClass(cls):
        # Sweeping seeds 0-39 once across the test suite to avoid duplicate computation.
        if cls._cached_results is None:
            cls._cached_results = [run_headless(seed=s, turns=30) for s in range(40)]

    @classmethod
    def _get_results(cls) -> list[GameResult]:
        if cls._cached_results is None:
            cls._cached_results = [run_headless(seed=s, turns=30) for s in range(40)]
        return cls._cached_results

    def test_simulation_balance_all_metrics(self):
        """Execute all empirical balance assertions in a single test method to avoid redundant runs."""
        results = self._get_results()
        self.assertEqual(len(results), 40)

        # 1. Winner distribution:
        # - Appears >= 3 different non-None winners
        # - Each faction wins at least 3 games
        # - faction_1 win ratio <= 0.70
        winners = [r.winner for r in results]
        non_none_winners = {w for w in winners if w is not None}
        self.assertGreaterEqual(
            len(non_none_winners),
            3,
            f"Expected at least 3 distinct non-None winners, got {non_none_winners}",
        )

        counts = Counter(winners)
        for fid in ("faction_1", "faction_2", "faction_3"):
            self.assertGreaterEqual(
                counts[fid],
                3,
                f"Faction {fid} must win at least 3 games across seeds 0-39, got {counts[fid]}",
            )

        faction_1_win_ratio = counts["faction_1"] / len(results)
        self.assertLessEqual(
            faction_1_win_ratio,
            0.70,
            f"Faction 1 win ratio ({faction_1_win_ratio:.3f}) exceeded cap of 0.70",
        )

        # 2. Rest action ratio across all decisions < 0.75
        total_decisions = sum(r.stats["decisions"] for r in results)
        rest_decisions = sum(
            sum(1 for event in r.events if event.action == "rest")
            for r in results
        )
        self.assertGreater(total_decisions, 0)
        rest_ratio = rest_decisions / total_decisions
        self.assertLess(
            rest_ratio,
            0.75,
            f"Rest action ratio ({rest_ratio:.3f}) exceeded bound of 0.75",
        )

        # 3. Decision validity and safety net:
        # stats['valid'] == stats['decisions'] and stats['fallbacks'] == 0 for every game
        for seed_idx, r in enumerate(results):
            self.assertEqual(
                r.stats["valid"],
                r.stats["decisions"],
                f"Seed {seed_idx}: valid count ({r.stats['valid']}) != decisions ({r.stats['decisions']})",
            )
            self.assertEqual(
                r.stats["fallbacks"],
                0,
                f"Seed {seed_idx}: fallback count was {r.stats['fallbacks']}, expected 0",
            )

        # 4. Final state diversity:
        # At least 5 distinct (all city owners, all city troops) combinations
        unique_final_states = {
            tuple(
                (cid, r.final_state.city(cid).owner, r.final_state.city(cid).troops)
                for cid in sorted(r.final_state.cities)
            )
            for r in results
        }
        self.assertGreaterEqual(
            len(unique_final_states),
            5,
            f"Expected at least 5 distinct final states, got {len(unique_final_states)}",
        )

    def test_winner_diversity_and_distribution(self):
        """Assert at least 3 distinct non-None winners emerge across seeds 0-39."""
        results = self._get_results()
        non_none_winners = {r.winner for r in results if r.winner is not None}
        self.assertGreaterEqual(len(non_none_winners), 3)

    def test_each_faction_minimum_wins_and_leader_cap(self):
        """Assert every faction wins at least 3 games and faction_1 win ratio <= 0.70."""
        results = self._get_results()
        counts = Counter(r.winner for r in results)
        for fid in ("faction_1", "faction_2", "faction_3"):
            self.assertGreaterEqual(counts[fid], 3)
        self.assertLessEqual(counts["faction_1"] / len(results), 0.70)

    def test_rest_action_ratio_below_cap(self):
        """Assert rest action ratio across all decisions is strictly under 0.75."""
        results = self._get_results()
        total_decisions = sum(r.stats["decisions"] for r in results)
        rest_decisions = sum(
            sum(1 for event in r.events if event.action == "rest")
            for r in results
        )
        self.assertLess(rest_decisions / total_decisions, 0.75)

    def test_safety_net_zero_fallbacks_and_valid_decisions(self):
        """Assert all decisions are valid and fallbacks == 0 for every game."""
        results = self._get_results()
        for r in results:
            self.assertEqual(r.stats["valid"], r.stats["decisions"])
            self.assertEqual(r.stats["fallbacks"], 0)

    def test_final_states_diversity(self):
        """Assert at least 5 distinct final state (owner, troops) combinations occur."""
        results = self._get_results()
        unique_final_states = {
            tuple(
                (cid, r.final_state.city(cid).owner, r.final_state.city(cid).troops)
                for cid in sorted(r.final_state.cities)
            )
            for r in results
        }
        self.assertGreaterEqual(len(unique_final_states), 5)


if __name__ == "__main__":
    unittest.main()
