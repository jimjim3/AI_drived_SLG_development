"""scripts/selfplay.py must attribute sieges to the LLM only when the LLM named the officer."""
import importlib.util
import pathlib
import unittest

from slg.agents.base import FactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.schema import AgentDecision, FactionPlan
from slg.sim.headless import run_headless

_spec = importlib.util.spec_from_file_location(
    "selfplay", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "selfplay.py")
selfplay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(selfplay)


class OneSiege(FactionAgent):
    """Turn 1: name guan_yu and order a siege on Xuchang; afterwards name nobody (everyone is delegated)."""

    def __init__(self):
        self.sent = False

    def decide(self, view):
        if self.sent:
            return FactionPlan()
        self.sent = True
        return FactionPlan(orders=(AgentDecision("guan_yu", "siege", {"to": "xuchang", "troops": 1000}),),
                           next_cast=("guan_yu",))


class SelfPlaySummaryTest(unittest.TestCase):
    def run_game(self):
        agents = {"faction_1": RuleBasedAgent("balanced"), "faction_2": OneSiege(), "faction_3": RuleBasedAgent("balanced")}
        return run_headless(seed=0, turns=3, agents_by_faction=agents, scenario="advantage")

    def test_llm_ordered_siege_is_counted_for_the_ordering_faction_only(self):
        r = selfplay.summarize(self.run_game(), 0)
        f2, f1, f3 = (r["factions"][k] for k in ("faction_2", "faction_1", "faction_3"))
        self.assertEqual(f2["sieges_llm"], 1)
        self.assertEqual((f1["sieges_llm"], f3["sieges_llm"]), (0, 0))

    def test_summary_shape_and_consistency(self):
        res = self.run_game()
        r = selfplay.summarize(res, 7)
        self.assertEqual(r["seed"], 7)
        self.assertEqual(set(r["factions"]), {"faction_1", "faction_2", "faction_3"})
        for f in r["factions"].values():
            self.assertLessEqual(f["captured_llm"], f["sieges_llm"])
            self.assertLessEqual(f["captured_delegated"], f["sieges_delegated"])
        total = sum(f["sieges_llm"] + f["sieges_delegated"] for f in r["factions"].values())
        self.assertEqual(total, sum(1 for e in res.events if e.action == "siege"))


if __name__ == "__main__":
    unittest.main()
