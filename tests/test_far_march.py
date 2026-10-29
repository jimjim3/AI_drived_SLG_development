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
