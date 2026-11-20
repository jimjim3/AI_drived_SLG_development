import dataclasses
import random
import unittest

from slg.engine import combat
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import resolve_decision
from slg.agents.rule_based import RuleBasedAgent
from slg.schema import AgentDecision


def recruit(state, officer, paid):
    new, ev = resolve_decision(state, officer, AgentDecision(officer.officer_id, "recruit", {"troops": paid}), random.Random(0))
    return new.cities[officer.city_id].troops - state.cities[officer.city_id].troops, ev


class RecruitLeadershipTest(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def pick(self, st, leadership):
        o = next(o for o in st.officers.values() if o.faction_id == "faction_1" and o.city_id == "xuchang")
        return dataclasses.replace(o, leadership=leadership)

    def test_default_ruleset_unchanged(self):
        st = build_initial_state("default")
        for lead in (20, 90):
            self.assertEqual(recruit(st, self.pick(st, lead), 500)[0], 500)

    def test_yield_scales_with_leadership(self):
        combat.set_rules("softer_pool2_econ4")
        st = build_initial_state("default")
        got = {lead: recruit(st, self.pick(st, lead), 400)[0] for lead in (25, 75, 100)}
        self.assertEqual(got, {25: 200, 75: 400, 100: 500})

    def test_legal_max_respects_capacity_after_yield(self):
        combat.set_rules("softer_pool2_econ4")
        st = build_initial_state("default")
        o = self.pick(st, 100)
        city = st.cities[o.city_id]
        _, _, cap = combat.city_caps(city.city_id)
        st = dataclasses.replace(st, cities={**st.cities, city.city_id: dataclasses.replace(city, gold=5000, troops=cap - 300)})
        la = next(a for a in generate_legal_actions(st, o) if a.action == "recruit")
        gained, _ = recruit(st, o, la.params["troops"].max)
        self.assertLessEqual(st.cities[o.city_id].troops + gained, cap)
        self.assertIn("leadership", la.note)

    def test_full_game_runs_and_rule_ai_stays_legal(self):
        combat.set_rules("softer_pool2_econ4")
        st = build_initial_state("default")
        g = Game(st, {f: RuleBasedAgent("balanced") for f in sorted(st.factions)}, random.Random(3))
        for _ in range(15):
            g.step()
        self.assertEqual(g.stats["orders_rejected"], 0)

    def test_ruleset_registered_and_web_default(self):
        self.assertTrue(combat.RULESETS["softer_pool2_econ4"].recruit_leadership)
        self.assertTrue(combat.RULESETS["softer_pool2_econ4_ally3"].alliance)
        from slg.web.server import WEB_DEFAULT_RULES
        self.assertTrue(combat.RULESETS[WEB_DEFAULT_RULES].recruit_leadership)


if __name__ == "__main__":
    unittest.main()
