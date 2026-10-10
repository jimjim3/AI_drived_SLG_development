"""Behavioral acceptance tests for loyalty, neglect, disobey, and defection mechanics."""

import unittest

from slg.agents.backends import _parse_legal_str
from slg.agents.base import FactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.schema import (
    CAST_LIMIT,
    AgentDecision,
    FactionPlan,
)
from slg.sim.headless import run_headless

ALL_FACTION_2_OFFICERS = [
    "zhuge_liang", "guan_yu", "zhang_fei", "zhao_yun", "huang_zhong", "wei_yan",
    "pang_tong", "fa_zheng", "ma_chao", "jiang_wei", "ma_liang", "xu_shu",
    "jian_yong", "sun_qian"
]


class StubbornAgent(FactionAgent):
    """Never issues orders; all officers are delegated to rule-based fallback."""

    def decide(self, view):
        return FactionPlan(orders=())


class FixedSixAgent(FactionAgent):
    """Always orders the exact same 6 officers each turn."""

    def __init__(self):
        self._fixed_six = None

    def decide(self, view):
        if self._fixed_six is None:
            self._fixed_six = tuple(c["id"] for c in view.cast[:CAST_LIMIT])

        orders = []
        cast_by_id = {c["id"]: c for c in view.cast}
        for oid in self._fixed_six:
            if oid in cast_by_id:
                c = cast_by_id[oid]
                for legal_str in c["legal"]:
                    act, params = _parse_legal_str(legal_str)
                    if act != "rest":
                        orders.append(AgentDecision(oid, act, params))
                        break
        return FactionPlan(orders=tuple(orders), next_cast=self._fixed_six)


class RotatorAgent(FactionAgent):
    """Prioritizes ordering officers with highest neglect, and rotates next_cast."""

    def __init__(self):
        self._rotation_idx = 0

    def decide(self, view):
        # 1. Orders: sort view.cast by neglect descending, order up to CAST_LIMIT
        sorted_cast = sorted(view.cast, key=lambda c: -c.get("neglect", 0))
        orders = []
        for c in sorted_cast[:CAST_LIMIT]:
            for legal_str in c["legal"]:
                act, params = _parse_legal_str(legal_str)
                if act != "rest":
                    orders.append(AgentDecision(c["id"], act, params))
                    break

        # 2. Next cast: rotate through all faction_2 officers so everyone is seen
        next_cast = tuple(
            ALL_FACTION_2_OFFICERS[(self._rotation_idx + i) % len(ALL_FACTION_2_OFFICERS)]
            for i in range(CAST_LIMIT)
        )
        self._rotation_idx = (self._rotation_idx + CAST_LIMIT) % len(ALL_FACTION_2_OFFICERS)
        return FactionPlan(orders=tuple(orders), next_cast=next_cast)


class TestAttentionBehavior(unittest.TestCase):
    def test_stubborn_agent_acceptance(self):
        # Stubborn: >= 50% of seeds 0-19 within 30 turns have at least 1 defection from faction_2.
        # Within the first 8 turns, defections in any seed <= 25% of the faction's officers (<= 3).
        seeds_with_defect = 0
        total_defects = 0
        total_disobey = 0
        max_early_defects = 0

        for seed in range(20):
            res = run_headless(
                seed=seed,
                turns=30,
                agents_by_faction={
                    "faction_1": RuleBasedAgent("balanced"),
                    "faction_2": StubbornAgent(),
                    "faction_3": RuleBasedAgent("balanced"),
                },
            )
            f2_defects = [
                inc for inc in res.incidents
                if inc.action == "defect" and inc.faction_id == "faction_2"
            ]
            if f2_defects:
                seeds_with_defect += 1
            total_defects += len(f2_defects)
            total_disobey += res.stats.get("disobeyed", 0)

            early = [inc for inc in f2_defects if inc.turn <= 8]
            max_early_defects = max(max_early_defects, len(early))

        ratio = seeds_with_defect / 20.0
        avg_defects = total_defects / 20.0
        # Expected: >= 50%
        self.assertGreaterEqual(
            ratio,
            0.50,
            f"Stubborn defection seed ratio {ratio:.1%} should be >= 50%",
        )
        # Expected: max early <= 25% of 14 officers (<= 3.5 -> <= 3)
        self.assertLessEqual(
            max_early_defects,
            int(len(ALL_FACTION_2_OFFICERS) * 0.25),
            f"Early defection max {max_early_defects} exceeds 25% of officers",
        )

    def test_fixed_six_agent_acceptance(self):
        # FixedSix: >= 50% of seeds 0-19 within 30 turns have at least 1 defection
        # among the remaining 8 officers of faction_2.
        seeds_with_defect = 0
        total_defects = 0
        total_disobey = 0

        for seed in range(20):
            agent = FixedSixAgent()
            res = run_headless(
                seed=seed,
                turns=30,
                agents_by_faction={
                    "faction_1": RuleBasedAgent("balanced"),
                    "faction_2": agent,
                    "faction_3": RuleBasedAgent("balanced"),
                },
            )
            f2_remaining_defects = [
                inc for inc in res.incidents
                if inc.action == "defect"
                and inc.faction_id == "faction_2"
                and inc.officer_id not in agent._fixed_six
            ]
            if f2_remaining_defects:
                seeds_with_defect += 1
            total_defects += len(f2_remaining_defects)
            total_disobey += res.stats.get("disobeyed", 0)

        ratio = seeds_with_defect / 20.0
        avg_defects = total_defects / 20.0
        # Expected: >= 50%
        self.assertGreaterEqual(
            ratio,
            0.50,
            f"FixedSix defection seed ratio {ratio:.1%} should be >= 50%",
        )

    def test_rotator_agent_acceptance(self):
        # Rotator: >= 90% of seeds 0-19 within 30 turns have ZERO defections for faction_2.
        zero_defect_seeds = 0
        total_defects = 0
        total_disobey = 0

        for seed in range(20):
            agent = RotatorAgent()
            res = run_headless(
                seed=seed,
                turns=30,
                agents_by_faction={
                    "faction_1": RuleBasedAgent("balanced"),
                    "faction_2": agent,
                    "faction_3": RuleBasedAgent("balanced"),
                },
            )
            f2_defects = [
                inc for inc in res.incidents
                if inc.action == "defect" and inc.faction_id == "faction_2"
            ]
            if len(f2_defects) == 0:
                zero_defect_seeds += 1
            total_defects += len(f2_defects)
            total_disobey += res.stats.get("disobeyed", 0)

        ratio = zero_defect_seeds / 20.0
        avg_defects = total_defects / 20.0
        # Expected: >= 90%
        self.assertGreaterEqual(
            ratio,
            0.90,
            f"Rotator zero-defection ratio {ratio:.1%} should be >= 90%",
        )

    def test_rule_based_baseline_acceptance(self):
        # All balanced rule-based agents: zero defect and zero disobey across all seeds 0-19.
        for seed in range(20):
            res = run_headless(seed=seed, turns=30)
            defects = [inc for inc in res.incidents if inc.action == "defect"]
            self.assertEqual(len(defects), 0, f"Seed {seed} had unexpected defection")
            self.assertEqual(res.stats.get("disobeyed", 0), 0, f"Seed {seed} had unexpected disobey")


if __name__ == "__main__":
    unittest.main()
