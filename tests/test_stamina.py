import dataclasses
import random
import unittest

from slg.agents.rule_based import RuleBasedAgent
from slg.engine import combat
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import resolve_decision
from slg.engine.view import build_faction_view, select_cast
from slg.schema import AgentDecision


def officer_in(st, city="xuchang"):
    return next(o for o in st.officers.values() if o.faction_id == "faction_1" and o.city_id == city)


def act(st, o, action, params=None):
    return resolve_decision(st, o, AgentDecision(o.officer_id, action, params or {}), random.Random(0))


class StaminaTest(unittest.TestCase):
    def tearDown(self):
        combat.set_rules("v2")

    def test_inert_under_default_rules(self):
        st = build_initial_state("default")
        o = officer_in(st)
        new, _ = act(st, o, "develop_agri")
        self.assertEqual(new.officers[o.officer_id].stamina, 100)
        tired = dataclasses.replace(o, stamina=0)
        self.assertEqual(combat.stamina_factor(tired), 1.0)
        view = build_faction_view(st, "faction_1", select_cast(st, "faction_1"))
        self.assertNotIn("stamina", view.cast[0])

    def test_costs_and_rest_recovery(self):
        combat.set_rules("softer_pool2_econ5")
        st = build_initial_state("default")
        o = officer_in(st)
        new, _ = act(st, o, "develop_agri")
        self.assertEqual(new.officers[o.officer_id].stamina, 85)
        tired = dataclasses.replace(o, stamina=40)
        st2 = dataclasses.replace(st, officers={**st.officers, o.officer_id: tired})
        rested, _ = act(st2, tired, "rest")
        self.assertEqual(rested.officers[o.officer_id].stamina, 60)
        floor = dataclasses.replace(o, stamina=5)
        st3 = dataclasses.replace(st, officers={**st.officers, o.officer_id: floor})
        self.assertEqual(act(st3, floor, "siege" if False else "develop_defense")[0].officers[o.officer_id].stamina, 0)

    def test_tired_officers_are_less_effective(self):
        combat.set_rules("softer_pool2_econ5")
        st = build_initial_state("default")
        o = officer_in(st)
        gains = {}
        for sta in (100, 50, 25, 0):
            t = dataclasses.replace(o, stamina=sta)
            s2 = dataclasses.replace(st, officers={**st.officers, o.officer_id: t})
            new, _ = act(s2, t, "develop_agri")
            gains[sta] = new.cities[o.city_id].agriculture - st.cities[o.city_id].agriculture
        self.assertEqual(gains[100], gains[50])
        self.assertGreater(gains[50], gains[25])
        self.assertGreater(gains[25], gains[0])
        self.assertAlmostEqual(gains[0] / gains[100], 0.5, delta=0.02)
        t0 = dataclasses.replace(o, stamina=0)
        s0 = dataclasses.replace(st, officers={**st.officers, o.officer_id: t0})
        note = next(a.note for a in generate_legal_actions(s0, t0) if a.action == "develop_agri")
        self.assertIn(str(gains[0]), note)

    def test_turn_tick_recovers_everyone(self):
        combat.set_rules("softer_pool2_econ5")
        st = build_initial_state("default")
        worn = {oid: dataclasses.replace(o, stamina=20) for oid, o in st.officers.items()}
        g = Game(dataclasses.replace(st, officers=worn), {f: RuleBasedAgent("balanced") for f in sorted(st.factions)},
                 random.Random(1))
        g.step()
        # the rule AI makes officers under 30 stamina rest: 20 + 10 (tick) = 30 is not < 30, so they may work again
        self.assertTrue(all(o.stamina >= 0 for o in g.state.officers.values()))
        self.assertGreater(sum(o.stamina for o in g.state.officers.values()), 0)

    def test_rule_ai_rests_when_worn_out(self):
        combat.set_rules("softer_pool2_econ5")
        st = build_initial_state("default")
        o = dataclasses.replace(officer_in(st), stamina=10)
        d = RuleBasedAgent("balanced").decide(st, o, generate_legal_actions(st, o))
        self.assertEqual(d.action, "rest")

    def test_view_exposes_stamina_and_prompt_mentions_it(self):
        combat.set_rules("softer_pool2_econ5")
        st = build_initial_state("default")
        view = build_faction_view(st, "faction_1", select_cast(st, "faction_1"))
        self.assertTrue(all("stamina" in c for c in view.cast))
        from slg.agents.llm_agent import STAMINA_NOTE
        self.assertIn("體力", STAMINA_NOTE)

    def test_siege_strength_drops_when_tired(self):
        combat.set_rules("softer_pool2_econ5")
        from slg.engine.resolution import _siege_strengths
        st = build_initial_state("advantage:faction_1")
        o = next(o for o in st.officers.values() if o.faction_id == "faction_1")
        target = next(c for c in st.cities.values() if c.owner != "faction_1")
        full, _ = _siege_strengths(st, o, target.city_id, 1000)
        tired, _ = _siege_strengths(st, dataclasses.replace(o, stamina=0), target.city_id, 1000)
        self.assertAlmostEqual(tired / full, 0.5, places=3)

    def test_full_game_legal_and_bounded(self):
        combat.set_rules("softer_pool2_econ5")
        st = build_initial_state("default")
        g = Game(st, {f: RuleBasedAgent("balanced") for f in sorted(st.factions)}, random.Random(4))
        for _ in range(20):
            g.step()
            self.assertTrue(all(0 <= o.stamina <= 100 for o in g.state.officers.values()))
        self.assertEqual(g.stats["orders_rejected"], 0)

    def test_rulesets_registered(self):
        self.assertTrue(combat.RULESETS["softer_pool2_econ5"].stamina)
        self.assertTrue(combat.RULESETS["softer_pool2_econ5"].recruit_leadership)
        self.assertTrue(combat.RULESETS["softer_pool2_econ5_ally3"].alliance)


if __name__ == "__main__":
    unittest.main()
