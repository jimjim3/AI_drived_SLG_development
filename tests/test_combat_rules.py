"""Experimental combat rule sets: the shipped rules (v2) are the default and unchanged; pooling is opt-in."""
import random
import unittest
from dataclasses import replace

from slg.engine import combat
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import estimate_siege_ratio, resolve_decision
from slg.schema import SIEGE_MIN_GARRISON, AgentDecision


def with_troops(state, **troops):
    cities = dict(state.cities)
    for cid, n in troops.items():
        cities[cid] = replace(cities[cid], troops=n)
    return replace(state, cities=cities)


def siege_spec(state, officer_id):
    o = state.officer(officer_id)
    return next((la for la in generate_legal_actions(state, o) if la.action == "siege"), None)


class RulesetBasics(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def test_shipped_rules_are_the_default(self):
        self.assertEqual(combat.active().name, "v2")
        self.assertEqual((combat.active().defense_divisor, combat.active().dq_base, combat.active().dq_div,
                          combat.active().pool_factor), (200.0, 0.5, 100.0, 0.0))

    def test_v2_matches_the_original_formula(self):
        state = build_initial_state("default")
        o = state.officer("xun_yu")
        target = state.city("luoyang")
        best = max((d.war + d.leadership) / 2 for d in state.officers.values()
                   if d.faction_id == target.owner and d.city_id == "luoyang")
        expected = (1000 * (0.5 + (o.war + o.leadership) / 200)) / (
            target.troops * (1 + target.defense / 200) * (0.5 + best / 100))
        self.assertAlmostEqual(estimate_siege_ratio(state, o, "luoyang", 1000), expected)

    def test_softer_rules_favour_the_attacker(self):
        state = build_initial_state("default")
        o = state.officer("xun_yu")
        base = estimate_siege_ratio(state, o, "luoyang", 1000)
        with combat.use_rules("softer"):
            self.assertGreater(estimate_siege_ratio(state, o, "luoyang", 1000), base)
        self.assertEqual(estimate_siege_ratio(state, o, "luoyang", 1000), base)  # restored

    def test_use_rules_restores_and_unknown_names_fail(self):
        with combat.use_rules("pool"):
            self.assertEqual(combat.active().name, "pool")
        self.assertEqual(combat.active().name, "v2")
        with self.assertRaises(ValueError):
            combat.set_rules("nope")


class Pooling(unittest.TestCase):
    def setUp(self):
        # xuchang is a Cao city adjacent to chenliu, xiangyang (both Cao) and luoyang (Liu)
        self.state = with_troops(build_initial_state("default"), xuchang=600, chenliu=2100, xiangyang=1100)

    def tearDown(self):
        combat.set_rules("v2")

    def test_without_pooling_only_the_origin_city_counts(self):
        spec = siege_spec(self.state, "xun_yu")
        self.assertEqual(spec.params["troops"].max, 500)
        self.assertEqual(combat.siege_capacity(self.state, self.state.city("xuchang")), 500)

    def test_pooling_adds_half_of_each_friendly_neighbour_spare(self):
        with combat.use_rules("pool"):
            cap = combat.siege_capacity(self.state, self.state.city("xuchang"))
            self.assertEqual(cap, 500 + 1000 + 500)  # origin + half of 2000 + half of 1000
            self.assertEqual(siege_spec(self.state, "xun_yu").params["troops"].max, 2000)

    def test_pooled_troops_are_deducted_from_the_cities_that_supplied_them(self):
        with combat.use_rules("pool"):
            for seed in range(6):
                decision = AgentDecision("xun_yu", "siege", {"to": "luoyang", "troops": 2000})
                new_state, event = resolve_decision(self.state, self.state.officer("xun_yu"), decision, random.Random(seed))
                drawn = {cid: self.state.city(cid).troops - new_state.city(cid).troops
                         for cid in ("xuchang", "chenliu", "xiangyang")}
                self.assertGreater(drawn["chenliu"], 0, "pooled neighbour must pay")
                self.assertLessEqual(sum(drawn.values()), 2000)
                for cid in ("xuchang", "chenliu", "xiangyang"):
                    self.assertGreaterEqual(new_state.city(cid).troops, SIEGE_MIN_GARRISON, cid)
                if event.captured_city:
                    self.assertEqual(sum(drawn.values()), 2000)  # a win consumes the whole expedition from the sources

    def test_contributions_sum_to_the_order(self):
        with combat.use_rules("pool"):
            parts = combat.siege_contributions(self.state, self.state.city("xuchang"), 1700)
            self.assertEqual(sum(a for _, a in parts), 1700)
            self.assertEqual(parts[0], ("xuchang", 500))

    def test_default_rules_deduct_from_the_origin_only(self):
        decision = AgentDecision("xun_yu", "siege", {"to": "luoyang", "troops": 500})
        new_state, _ = resolve_decision(self.state, self.state.officer("xun_yu"), decision, random.Random(0))
        self.assertEqual(new_state.city("chenliu").troops, 2100)
        self.assertEqual(new_state.city("xiangyang").troops, 1100)


if __name__ == "__main__":
    unittest.main()
