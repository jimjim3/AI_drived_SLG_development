"""Evaluation reports how close officers got to the defect / petition thresholds."""
import unittest

from slg.agents.base import FactionAgent
from slg.engine.initial_state import build_initial_state
from slg.schema import DEFECT_BELOW, FactionPlan
from slg.sim.evaluate import evaluate


class NamesNobody(FactionAgent):
    """Never gives an order and never names anyone, so every officer is neglected (delegates act instead)."""

    def decide(self, view):
        return FactionPlan()


class LoyaltyDiagnosticsTest(unittest.TestCase):
    def run_eval(self, turns):
        return evaluate(seeds=[0], turns=turns, seat="faction_2", agent_factory=lambda: NamesNobody())

    def test_incident_fields_are_reported_for_both_arms(self):
        inc = self.run_eval(3)["per_seed"][0]["diagnostics"]["incidents"]
        for arm in ("baseline", "experiment"):
            self.assertIn("final_min_loyalty", inc[arm])
            self.assertIn("final_max_neglect", inc[arm])
            self.assertLessEqual(inc[arm]["final_min_loyalty"], inc[arm]["final_avg_loyalty"])

    def test_neglect_shows_up_and_loyalty_falls_when_nobody_is_named(self):
        short = self.run_eval(2)["per_seed"][0]["diagnostics"]["incidents"]["experiment"]
        long_ = self.run_eval(12)["per_seed"][0]["diagnostics"]["incidents"]["experiment"]
        self.assertGreaterEqual(long_["final_max_neglect"], short["final_max_neglect"])
        self.assertLessEqual(long_["final_min_loyalty"], short["final_min_loyalty"])
        initial_loyalties = [o.loyalty for o in build_initial_state().officers.values() if o.faction_id == "faction_2"]
        self.assertLess(long_["final_min_loyalty"], max(initial_loyalties))
        self.assertGreaterEqual(DEFECT_BELOW, 0)

    def test_summary_aggregates_min_across_seeds(self):
        res = evaluate(seeds=[0, 1], turns=4, seat="faction_2", agent_factory=lambda: NamesNobody())
        mins = [s["diagnostics"]["incidents"]["experiment"]["final_min_loyalty"] for s in res["per_seed"]]
        self.assertEqual(res["summary"]["diagnostics"]["incidents"]["experiment"]["final_min_loyalty"], min(mins))


if __name__ == "__main__":
    unittest.main()
