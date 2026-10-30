"""Distance: a siege over a far edge (宛—漢中, 襄陽—建業) is weakened only under the *_far ruleset."""
import unittest
from dataclasses import replace

from slg.engine import combat
from slg.engine.initial_state import build_initial_state
from slg.engine.resolution import estimate_siege_ratio


class FarMarch(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def _state_and_officer(self):
        s = build_initial_state("default")
        cities = dict(s.cities)
        cities["hanzhong"] = replace(cities["hanzhong"], owner="faction_1")  # enemy behind the far edge
        s = replace(s, cities=cities)
        o = next(o for o in s.officers.values() if o.faction_id == "faction_2" and o.city_id == "wancheng")
        return s, o

    def test_far_edge_weakens_attacker_only_in_far_rules(self):
        s, o = self._state_and_officer()
        ratios = {}
        for name in ("softer_pool2", "softer_pool2_far"):
            combat.set_rules(name)
            ratios[name] = estimate_siege_ratio(s, o, "hanzhong", 700)
        self.assertAlmostEqual(ratios["softer_pool2_far"], ratios["softer_pool2"] * 0.75, places=6)

    def test_near_edge_unaffected(self):
        s, o = self._state_and_officer()
        combat.set_rules("softer_pool2")
        a = estimate_siege_ratio(s, o, "luoyang", 700)
        combat.set_rules("softer_pool2_far")
        self.assertAlmostEqual(estimate_siege_ratio(s, o, "luoyang", 700), a, places=6)
        self.assertEqual(combat.far_march_factor("luoyang", "xuchang"), 0.75 / 0.75)

    def test_default_rules_ignore_distance(self):
        self.assertEqual(combat.far_march_factor("wancheng", "hanzhong"), 1.0)


if __name__ == "__main__":
    unittest.main()


class EconomyRules(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def test_default_has_no_caps_or_march_food(self):
        self.assertEqual(combat.march_food("xiangyang", "jianye", 800), 0)
        self.assertEqual(combat.city_caps("kuaiji")[2], combat.UNCAPPED)

    def test_march_food_grows_with_distance(self):
        combat.set_rules("softer_pool2_econ")
        near = combat.march_food("chenliu", "xuchang", 800)
        far = combat.march_food("xiangyang", "jianye", 800)
        self.assertEqual(near, 81)
        self.assertEqual(far, 502)

    def test_recruit_and_develop_respect_caps(self):
        from slg.engine.legal_actions import generate_legal_actions
        combat.set_rules("softer_pool2_econ")
        s = build_initial_state("default")
        c = dict(s.cities)
        c["kuaiji"] = replace(c["kuaiji"], troops=1100, agriculture=550, gold=5000)
        s = replace(s, cities=c)
        o = next(o for o in s.officers.values() if o.city_id == "kuaiji" and o.faction_id == "faction_3")
        acts = {a.action for a in generate_legal_actions(s, o)}
        self.assertNotIn("recruit", acts)
        self.assertNotIn("develop_agri", acts)
        self.assertIn("develop_commerce", acts)

    def test_siege_rejected_without_food(self):
        from slg.engine.validation import validate_decision
        from slg.schema import AgentDecision
        combat.set_rules("softer_pool2_econ")
        s = build_initial_state("default")
        c = dict(s.cities)
        c["xiangyang"] = replace(c["xiangyang"], troops=3000, food=100)
        s = replace(s, cities=c)
        o = next(o for o in s.officers.values() if o.city_id == "xiangyang" and o.faction_id == "faction_1")
        ok, why = validate_decision(s, o, AgentDecision(o.officer_id, "siege", {"to": "jianye", "troops": 1000}, ""))
        self.assertFalse(ok)
        self.assertIn("food", why)

    def test_econ3_ruleset(self):
        combat.set_rules("softer_pool2_econ3")
        self.assertEqual(combat.active().march_food_rate, 0.5)
        self.assertEqual(combat.march_food("xiangyang", "jianye", 800), 251)
        self.assertEqual(combat.city_caps("kuaiji")[2], 1100)

    def test_flat_tier_caps(self):
        rule = replace(combat.RULESETS["softer_pool2_econ2"], cap_tiers="flat")
        combat.RULESETS["_test_flat"] = rule
        try:
            combat.set_rules("_test_flat")
            self.assertEqual(combat.city_caps("kuaiji")[2], 1750)
            self.assertEqual(combat.city_caps("jianye")[2], 2200)
        finally:
            combat.set_rules("v2")
            del combat.RULESETS["_test_flat"]
