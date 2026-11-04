"""Alliances (docs/DESIGN_ALLIANCE.md phase 1): inert under shipped rules, active under *_ally."""
import random
import unittest

from slg.engine import alliance, combat
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import resolve_decision
from slg.engine.validation import validate_decision
from slg.engine.view import build_faction_view
from slg.schema import AgentDecision

RULES = "softer_pool2_econ3_ally"


def envoy(state, fid):
    return state.officer(alliance.envoy_id(state, fid))


def propose(state, a, b, accept=None):
    o = envoy(state, a)
    return resolve_decision(state, o, AgentDecision(o.officer_id, "propose_alliance", {"to": b}),
                            random.Random(0), alliance_accept=accept)


class AllianceTests(unittest.TestCase):
    def setUp(self):
        combat.set_rules(RULES)
        self.s = build_initial_state("default")

    def tearDown(self):
        combat.set_rules("v2")

    def test_inert_under_default_rules(self):
        combat.set_rules("v2")
        for o in self.s.officers.values():
            acts = {la.action for la in generate_legal_actions(self.s, o)}
            self.assertFalse(acts & {"propose_alliance", "break_alliance"})
        v = build_faction_view(self.s, "faction_1", ())
        self.assertNotIn("diplomacy", v.to_dict())

    def test_only_the_envoy_may_propose(self):
        e = envoy(self.s, "faction_1")
        self.assertIn("propose_alliance", {la.action for la in generate_legal_actions(self.s, e)})
        others = [o for o in self.s.officers_of("faction_1") if o.officer_id != e.officer_id]
        for o in others:
            self.assertNotIn("propose_alliance", {la.action for la in generate_legal_actions(self.s, o)})

    def test_accept_forms_alliance_and_blocks_sieges(self):
        s, ev = propose(self.s, "faction_1", "faction_2")
        self.assertTrue(alliance.allied(s, "faction_1", "faction_2"))
        self.assertIn("accepted", ev.detail)
        self.assertGreaterEqual(alliance.friendship(s, "faction_1", "faction_2"), 60)
        for o in s.officers_of("faction_1"):
            for la in generate_legal_actions(s, o):
                if la.action == "siege":
                    for t in la.params["to"].choices:
                        self.assertNotEqual(s.city(t).owner, "faction_2")

    def test_refusal_sets_cooldown(self):
        s, _ = propose(self.s, "faction_1", "faction_2", accept=False)
        self.assertFalse(alliance.allied(s, "faction_1", "faction_2"))
        self.assertFalse(alliance.can_propose(s, "faction_1", "faction_2"))

    def test_low_friendship_is_refused_by_the_rule_ai(self):
        s = alliance.adjust(self.s, "faction_1", "faction_2", -30)
        s, ev = propose(s, "faction_1", "faction_2")
        self.assertIn("refused", ev.detail)

    def test_break_punishes_all_allies_and_blocks_reproposal(self):
        s, _ = propose(self.s, "faction_1", "faction_2")
        s, _ = propose(s, "faction_1", "faction_3")
        before3 = alliance.friendship(s, "faction_1", "faction_3")
        e = envoy(s, "faction_1")
        s, ev = resolve_decision(s, e, AgentDecision(e.officer_id, "break_alliance", {"with": "faction_2"}),
                                 random.Random(0))
        self.assertFalse(alliance.allied(s, "faction_1", "faction_2"))
        self.assertTrue(alliance.allied(s, "faction_1", "faction_3"))
        self.assertEqual(alliance.friendship(s, "faction_1", "faction_3"), before3 - alliance.BREAK_OTHER_PENALTY)
        self.assertLessEqual(alliance.friendship(s, "faction_1", "faction_2"), 60 - alliance.BREAK_VICTIM_PENALTY)
        self.assertFalse(alliance.can_propose(s, "faction_1", "faction_2"))

    def test_validation_rejects_siege_on_an_ally(self):
        s, _ = propose(self.s, "faction_1", "faction_2")
        o = next(o for o in s.officers_of("faction_1") if o.city_id)
        target = next(c.city_id for c in s.cities_of("faction_2"))
        bad = AgentDecision(o.officer_id, "siege", {"to": target, "troops": 500})
        self.assertFalse(validate_decision(s, o, bad)[0])

    def test_view_shares_vision_and_lists_relations(self):
        s, _ = propose(self.s, "faction_1", "faction_2")
        v = build_faction_view(s, "faction_1", ()).to_dict()
        self.assertEqual({d["faction"] for d in v["diplomacy"]}, {"faction_2", "faction_3"})
        self.assertTrue(next(d for d in v["diplomacy"] if d["faction"] == "faction_2")["allied"])
        plain = build_faction_view(self.s, "faction_1", ()).to_dict()
        self.assertGreater(len(v["frontier"]), len(plain["frontier"]))
        self.assertTrue(any(f.get("via_ally") for f in v["frontier"]))

    def test_tick_warms_strangers_and_cools_allies(self):
        s = alliance.adjust(self.s, "faction_1", "faction_3", -10)
        s2 = alliance.tick(s)
        self.assertEqual(alliance.friendship(s2, "faction_1", "faction_3"), 41)
        s, _ = propose(self.s, "faction_1", "faction_2")
        from dataclasses import replace
        s = replace(s, turn=3)
        self.assertEqual(alliance.friendship(alliance.tick(s), "faction_1", "faction_2"), 59)

    def test_full_game_runs_deterministically(self):
        from slg.agents.rule_based import RuleBasedAgent
        outs = []
        for _ in range(2):
            s = build_initial_state("default")
            g = Game(s, {f: RuleBasedAgent("balanced") for f in s.factions}, random.Random(3))
            g.run(10)
            outs.append(sorted((c.city_id, c.owner, c.troops) for c in g.state.cities.values()))
        self.assertEqual(outs[0], outs[1])

    def test_llm_agent_response_hook(self):
        from slg.agents.llm_agent import LLMFactionAgent
        yes = LLMFactionAgent(lambda sp, up: '{"accept": true, "reason": "ok"}')
        no = LLMFactionAgent(lambda sp, up: "not json")
        self.assertTrue(yes.respond_alliance(self.s, "faction_1", "faction_2"))
        low = alliance.adjust(self.s, "faction_1", "faction_2", -30)
        self.assertFalse(no.respond_alliance(low, "faction_1", "faction_2"))  # falls back to the rule


if __name__ == "__main__":
    unittest.main()
