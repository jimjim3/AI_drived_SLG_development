import unittest

from slg.engine import combat
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import ACTION_USES, generate_legal_actions
from slg.web.payload import legal_structured


class ActionAbilityTest(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def test_every_legal_action_declares_its_abilities(self):
        for rules in ("v2", "softer_pool2_econ3_ally3"):
            combat.set_rules(rules)
            st = build_initial_state("default")
            for o in st.officers.values():
                for la in generate_legal_actions(st, o):
                    self.assertIn(la.action, ACTION_USES, la.action)

    def test_payload_rank_and_best(self):
        st = build_initial_state("default")
        f2 = [o for o in st.officers.values() if o.faction_id == "faction_2"]
        best = max(f2, key=lambda o: (o.politics, o.officer_id))
        la = next(a for a in legal_structured(st, best.officer_id) if a["action"] == "develop_agri")
        u = la["uses"][0]
        self.assertEqual((u["stat"], u["value"], u["rank"], u["best_value"]), ("politics", best.politics, 1, best.politics))
        worst = min(f2, key=lambda o: (o.politics, o.officer_id))
        u2 = next(a for a in legal_structured(st, worst.officer_id) if a["action"] == "develop_agri")["uses"][0]
        self.assertEqual(u2["best_name"], best.name)
        self.assertGreater(u2["rank"], 1)

    def test_recruit_and_move_do_not_depend_on_officer(self):
        st = build_initial_state("default")
        o = next(iter(st.officers.values()))
        for a in legal_structured(st, o.officer_id):
            if a["action"] in ("recruit", "move", "rest"):
                self.assertEqual(a["uses"], [])

    def test_siege_uses_war_and_leadership(self):
        combat.set_rules("softer_pool2_econ3")
        st = build_initial_state("advantage:faction_1")
        for o in st.officers.values():
            sg = [a for a in legal_structured(st, o.officer_id) if a["action"] == "siege"]
            if sg:
                self.assertEqual([u["stat"] for u in sg[0]["uses"]], ["war", "leadership"])
                return
        self.fail("no siege option found in the advantage scenario")


if __name__ == "__main__":
    unittest.main()
