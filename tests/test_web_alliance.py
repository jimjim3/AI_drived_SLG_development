import time
import unittest

from slg.engine import combat
from slg.web.session import Session
from tests.test_web_session import wait_phase


class WebAllianceTest(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def test_default_payload_has_no_diplomacy(self):
        combat.set_rules("v2")
        s = Session(seed=1, turns=2, human_timeout=5)
        s.start()
        wait_phase(s, "awaiting_input")
        self.assertEqual(s.state().get("diplomacy", []), [])

    def test_alliance_payload_and_proposal_via_plan(self):
        combat.set_rules("softer_pool2_econ3_ally3")
        s = Session(seed=1, turns=3, human_timeout=5)
        s.start()
        wait_phase(s, "awaiting_input")
        st = s.state()
        self.assertEqual(len(st["diplomacy"]), 2)
        self.assertTrue(all(0 <= d["friendship"] <= 100 and d["allied"] is False for d in st["diplomacy"]))
        envoy = next(c for c in st["cast"] if any(la["action"] == "propose_alliance" for la in c["legal_structured"]))
        la = next(a for a in envoy["legal_structured"] if a["action"] == "propose_alliance")
        self.assertIn("pledge", la["params"])
        target = la["params"]["to"]["choices"][0]
        s.submit_plan({"orders": [{"officer": envoy["id"], "action": "propose_alliance",
                                   "params": {"to": target, "pledge": 0}}], "next_cast": []})
        wait_phase(s, "awaiting_input")
        while s.state() is None or s.game.state.turn < 2:
            time.sleep(0.01)
        self.assertEqual(s.status()["error"], None)


if __name__ == "__main__":
    unittest.main()
