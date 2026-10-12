"""Unit tests for loyalty, neglect, disobey, and defection mechanics."""

import random
import unittest
from dataclasses import replace

from slg.agents.base import Agent, FactionAgent
from slg.agents.llm_agent import SYSTEM_PROMPT
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.view import build_faction_view, forced_cast
from slg.schema import (
    CAST_LIMIT,
    DEFECT_BELOW,
    DEFECT_REJOIN_LOYALTY,
    DISOBEY_BELOW,
    LOYALTY_BOOST,
    LOYALTY_MAX,
    NEGLECT_PENALTY_START,
    NEGLECT_PETITION,
    PETITION_LOYALTY_BELOW,
    AgentDecision,
    FactionPlan,
    ResolutionEvent,
)


class MockRNG(random.Random):
    """RNG subclass returning pre-set floats for deterministic probability checks."""

    def __init__(self, values):
        super().__init__(42)
        self.values = list(values)
        self.call_count = 0

    def random(self):
        self.call_count += 1
        if self.values:
            return self.values.pop(0)
        return 0.5


class ScriptedFactionAgent(FactionAgent):
    def __init__(self, orders=(), next_cast=()):
        self._orders = orders
        self._next_cast = next_cast

    def decide(self, view):
        return FactionPlan(orders=self._orders, next_cast=self._next_cast)


class TestLoyaltyMechanics(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()

    def test_noticed_definition_rest_not_noticed(self):
        # Explicit 'rest' order is executed but not noticed
        officer = self.state.officer("xun_yu")
        self.assertEqual(officer.neglect, 0)
        agent = ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "rest"),))
        game = Game(
            self.state,
            {"faction_1": agent, "faction_2": ScriptedFactionAgent(), "faction_3": ScriptedFactionAgent()},
            random.Random(42),
        )
        game.step()
        updated = game.state.officer("xun_yu")
        # Since rest is not noticed, neglect increments by 1
        self.assertEqual(updated.neglect, 1)

    def test_noticed_definition_beyond_cast_limit_not_noticed(self):
        # Faction_1 has 14 officers. Order 7 valid non-rest orders.
        # First 6 should be noticed (neglect=0), 7th should NOT be noticed (neglect=1).
        officers_to_order = [
            "xun_yu", "xiahou_dun", "cao_ren", "dian_wei", "jia_xu", "li_dian", "yue_jin"
        ]
        orders = tuple(AgentDecision(oid, "develop_agri") for oid in officers_to_order)
        agent = ScriptedFactionAgent(orders=orders)
        game = Game(
            self.state,
            {"faction_1": agent, "faction_2": ScriptedFactionAgent(), "faction_3": ScriptedFactionAgent()},
            random.Random(42),
        )
        game.step()

        # First 6 noticed -> neglect=0
        for oid in officers_to_order[:CAST_LIMIT]:
            self.assertEqual(game.state.officer(oid).neglect, 0, f"{oid} should be noticed")
        # 7th officer beyond CAST_LIMIT -> neglect=1
        seventh = officers_to_order[CAST_LIMIT]
        self.assertEqual(game.state.officer(seventh).neglect, 1, f"{seventh} should not be noticed")

    def test_noticed_definition_disobeyed_order_not_noticed(self):
        # Officer with low loyalty disobeys, action becomes rest -> not noticed
        officer = self.state.officer("xun_yu")
        # Set loyalty=40 (< DISOBEY_BELOW=50), ambition=50
        # p = (50 - 40)/100 * (0.5 + 50/100) = 0.1 * 1.0 = 0.1
        # Fixed RNG returns 0.05 < 0.1 -> disobeys!
        low_state = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=40, ambition=50)},
        )

        class DisobeyRNG(random.Random):
            def random(self):
                return 0.05

        agent = ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))
        game = Game(
            low_state,
            {"faction_1": agent, "faction_2": ScriptedFactionAgent(), "faction_3": ScriptedFactionAgent()},
            DisobeyRNG(42),
        )
        game.step()

        self.assertEqual(game.stats["disobeyed"], 1)
        # Because it became rest, xun_yu is NOT noticed -> neglect=1
        self.assertEqual(game.state.officer("xun_yu").neglect, 1)

    def test_noticed_definition_rejected_order_not_noticed(self):
        # Invalid order (e.g. invalid action or unaffordable) is rejected and not noticed
        agent = ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "recruit", {"troops": 999999}),))
        game = Game(
            self.state,
            {"faction_1": agent, "faction_2": ScriptedFactionAgent(), "faction_3": ScriptedFactionAgent()},
            random.Random(42),
        )
        game.step()
        self.assertGreater(game.stats["orders_rejected"], 0)
        self.assertEqual(game.state.officer("xun_yu").neglect, 1)

    def test_neglect_penalty_progression_by_turn(self):
        # Test neglect and loyalty step by step (NEGLECT_PENALTY_START = 4):
        # Starting loyalty = 80.
        # Turn 1: neglect=1, penalty=0 -> loyalty=80
        # Turn 2: neglect=2, penalty=0 -> loyalty=80
        # Turn 3: neglect=3, penalty=0 -> loyalty=80
        # Turn 4: neglect=4, penalty=4-4+1=1 -> loyalty=79
        # Turn 5: neglect=5, penalty=5-4+1=2 -> loyalty=77
        # Turn 6: neglect=6, penalty=6-4+1=3 -> loyalty=74
        # Turn 7: neglect=7, penalty=7-4+1=4 -> loyalty=70
        # Turn 8: neglect=8, penalty=8-4+1=5 -> loyalty=65
        officer = self.state.officer("xun_yu")
        cur_state = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=80, neglect=0)},
        )
        expected_loyalties = [80, 80, 80, 79, 77, 74, 70, 65]
        expected_neglects = [1, 2, 3, 4, 5, 6, 7, 8]

        agent = ScriptedFactionAgent(orders=())  # empty orders so xun_yu is not noticed
        game = Game(
            cur_state,
            {"faction_1": agent, "faction_2": ScriptedFactionAgent(), "faction_3": ScriptedFactionAgent()},
            random.Random(42),
        )

        for turn_idx in range(8):
            game.step()
            o = game.state.officer("xun_yu")
            self.assertEqual(o.neglect, expected_neglects[turn_idx])
            self.assertEqual(o.loyalty, expected_loyalties[turn_idx])

    def test_loyalty_boost_and_cap_at_100(self):
        # Notice officer: neglect resets to 0, loyalty increases by 1, capped at LOYALTY_MAX=100
        officer = self.state.officer("xun_yu")
        state_99 = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=99, neglect=3)},
        )
        agent = ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))
        game = Game(
            state_99,
            {"faction_1": agent, "faction_2": ScriptedFactionAgent(), "faction_3": ScriptedFactionAgent()},
            random.Random(42),
        )
        game.step()
        o = game.state.officer("xun_yu")
        self.assertEqual(o.neglect, 0)
        self.assertEqual(o.loyalty, 100)

        # Another notice: should cap at 100
        game.step()
        o2 = game.state.officer("xun_yu")
        self.assertEqual(o2.loyalty, 100)

    def test_officer_level_agents_do_not_apply_neglect_or_disobey(self):
        # RuleBasedAgent is an officer-level Agent, not FactionAgent.
        # Neglect should not increase, and disobedience should never trigger.
        rb_agent = RuleBasedAgent("balanced")
        agents = {fid: rb_agent for fid in self.state.factions}
        game = Game(self.state, agents, random.Random(42))
        for _ in range(10):
            game.step()

        for o in game.state.officers.values():
            self.assertEqual(o.neglect, 0)
        self.assertEqual(game.stats["disobeyed"], 0)

    def test_disobey_probability_boundary(self):
        # DISOBEY_BELOW = 50.
        # loyalty = 50: does NOT roll RNG.
        # loyalty = 49: rolls RNG.
        o50 = self.state.officer("xun_yu")
        s50 = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(o50, loyalty=50, ambition=50)},
        )
        mock_rng_50 = MockRNG([0.01])
        g50 = Game(
            s50,
            {"faction_1": ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))},
            mock_rng_50,
        )
        # We manually step just the orders part or run step()
        # Since income also rolls uniforms, let's test disobedience check directly
        # or isolate disobedience by counting calls after income
        g50.step()
        self.assertEqual(g50.stats["disobeyed"], 0)

        # Now test exact hand-calculation of u < p and u >= p with fixed RNG
        # loyalty=40, ambition=50 -> p = (50 - 40)/100 * (0.5 + 50/100) = 0.10.
        # When u = 0.05 (< 0.10), disobeys -> action becomes rest, LogEntry.source="disobey"
        # When u = 0.15 (>= 0.10), obeys -> action remains develop_agri, LogEntry.source="order"
        s40 = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(o50, loyalty=40, ambition=50)},
        )

        # Subclass rng that returns 0.05 for disobey roll
        class ControlledDisobeyRNG(random.Random):
            def __init__(self, target_u):
                super().__init__(42)
                self.target_u = target_u
                self.disobey_rolled = False

            def random(self):
                # When random() is called during disobey check (after income which uses uniform)
                self.disobey_rolled = True
                return self.target_u

        rng_disobey = ControlledDisobeyRNG(0.05)
        g_disobey = Game(
            s40,
            {"faction_1": ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))},
            rng_disobey,
        )
        g_disobey.step()
        self.assertTrue(rng_disobey.disobey_rolled)
        self.assertEqual(g_disobey.stats["disobeyed"], 1)
        entry_disobey = [e for e in g_disobey.log_entries if e.officer_id == "xun_yu"][0]
        self.assertEqual(entry_disobey.source, "disobey")
        self.assertEqual(entry_disobey.action, "rest")
        self.assertIn("抗旨: 忠誠40 野心50 原令develop_agri", entry_disobey.event.detail)

        # When u = 0.15 >= 0.10 -> obeys
        rng_obey = ControlledDisobeyRNG(0.15)
        g_obey = Game(
            s40,
            {"faction_1": ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))},
            rng_obey,
        )
        g_obey.step()
        self.assertEqual(g_obey.stats["disobeyed"], 0)
        entry_obey = [e for e in g_obey.log_entries if e.officer_id == "xun_yu"][0]
        self.assertEqual(entry_obey.source, "order")
        self.assertEqual(entry_obey.action, "develop_agri")

    def test_rejected_order_does_not_roll_disobey(self):
        # Order rejected by basic validation should NOT roll RNG for disobedience
        officer = self.state.officer("xun_yu")
        s40 = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=30, ambition=50)},
        )

        class SpyRNG(random.Random):
            def __init__(self):
                super().__init__(42)
                self.random_called = False

            def random(self):
                self.random_called = True
                return 0.01

        spy = SpyRNG()
        # Invalid decision (illegal recruit amount)
        agent = ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "recruit", {"troops": 999999}),))
        g = Game(s40, {"faction_1": agent}, spy)
        g.step()
        self.assertEqual(g.stats["orders_rejected"], 1)
        self.assertEqual(g.stats["disobeyed"], 0)

    def test_delegated_officers_do_not_roll_disobey(self):
        # Delegated officers must never roll disobedience even if loyalty < 50
        officer = self.state.officer("xun_yu")
        s20 = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=20, ambition=90)},
        )
        # Empty orders -> all delegated
        agent = ScriptedFactionAgent(orders=())
        g = Game(s20, {"faction_1": agent}, random.Random(42))
        g.step()
        self.assertEqual(g.stats["disobeyed"], 0)
        entry = [e for e in g.log_entries if e.officer_id == "xun_yu"][0]
        self.assertEqual(entry.source, "delegate")

    def test_feedback_contains_disobey_message(self):
        # Disobeyed officer message appears in next turn's feedback: "{officer_id} 抗旨（忠誠{loyalty}）"
        officer = self.state.officer("xun_yu")
        s40 = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=40, ambition=50)},
        )

        class ForceDisobeyRNG(random.Random):
            def random(self):
                return 0.001

        agent = ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))
        g = Game(s40, {"faction_1": agent}, ForceDisobeyRNG(42))
        g.step()
        self.assertIn("xun_yu 抗旨（忠誠40）", g.feedback.get("faction_1", ()))

    def test_defection_conditions_and_rng_consumption_parity(self):
        # Defection consumes exactly one rng.random() for any officer with loyalty < DEFECT_BELOW
        # whether they have adjacent enemy cities or not.
        # Compare two games identical except game A has an adjacent enemy city and game B has no adjacent enemy city.
        # The subsequent RNG stream after turn 1 must be IDENTICAL.
        base = build_initial_state()
        # Set xun_yu in chenliu with loyalty=20 (< 35).
        # Chenliu borders xuchang.
        # In Game A: xuchang is owner="faction_2" (enemy).
        # In Game B: xuchang is owner="faction_1" (friendly).
        # Both games start with seed 12345.
        c_xuchang = base.city("xuchang")
        o_xunyu = base.officer("xun_yu")

        state_a = replace(
            base,
            cities={**base.cities, "xuchang": replace(c_xuchang, owner="faction_2")},
            officers={**base.officers, "xun_yu": replace(o_xunyu, city_id="chenliu", loyalty=20, ambition=60)},
        )
        state_b = replace(
            base,
            cities={**base.cities, "xuchang": replace(c_xuchang, owner="faction_1")},
            officers={**base.officers, "xun_yu": replace(o_xunyu, city_id="chenliu", loyalty=20, ambition=60)},
        )

        rng_a = random.Random(12345)
        rng_b = random.Random(12345)

        g_a = Game(state_a, {"faction_1": ScriptedFactionAgent()}, rng_a)
        g_b = Game(state_b, {"faction_1": ScriptedFactionAgent()}, rng_b)

        g_a.step()
        g_b.step()

        # In g_a, xun_yu defected to faction_2
        self.assertTrue(any(inc.officer_id == "xun_yu" and inc.action == "defect" for inc in g_a.incidents))
        # In g_b, xun_yu did not defect (no enemy city)
        self.assertFalse(any(inc.officer_id == "xun_yu" and inc.action == "defect" for inc in g_b.incidents))

        # But RNG state consumed MUST be identical, so next rolls match exactly
        rolls_a = [rng_a.random() for _ in range(10)]
        rolls_b = [rng_b.random() for _ in range(10)]
        self.assertEqual(rolls_a, rolls_b)

    def test_defection_target_city_and_updated_fields(self):
        # Target city is lexicographically smallest adjacent enemy city.
        # Officer fields updated: faction_id=new_owner, city_id=target_city, loyalty=DEFECT_REJOIN_LOYALTY=60, neglect=0.
        base = build_initial_state()
        # Put xun_yu at luoyang (borders xuchang, xiangyang, wancheng).
        # xun_yu faction is faction_2.
        # Adjacent enemy cities: xuchang (faction_1), xiangyang (faction_1).
        # Lexicographically smallest is xiangyang vs xuchang: 'xiangyang' < 'xuchang' is False ('x' matches, 'i' vs 'u': 'xiangyang' is smaller!).
        o = base.officer("xun_yu")
        s = replace(
            base,
            officers={**base.officers, "xun_yu": replace(o, faction_id="faction_2", city_id="luoyang", loyalty=10, ambition=80, neglect=10)},
        )

        class DefectRNG(random.Random):
            def random(self):
                return 0.001

        g = Game(s, {"faction_2": ScriptedFactionAgent()}, DefectRNG(42))
        g.step()

        self.assertEqual(len(g.incidents), 1)
        inc = g.incidents[0]
        self.assertEqual(inc.action, "defect")
        self.assertEqual(inc.officer_id, "xun_yu")
        self.assertEqual(inc.faction_id, "faction_2")
        self.assertEqual(inc.city_id, "xiangyang")
        self.assertIn("faction_2 -> faction_1", inc.detail)

        updated_o = g.state.officer("xun_yu")
        self.assertEqual(updated_o.faction_id, "faction_1")
        self.assertEqual(updated_o.city_id, "xiangyang")
        self.assertEqual(updated_o.loyalty, DEFECT_REJOIN_LOYALTY)
        self.assertEqual(updated_o.neglect, 0)

    def test_incidents_do_not_enter_events_and_appear_in_next_view(self):
        # Game.incidents must NOT be appended to self.events
        # Invariant len(events) == decisions must hold
        base = build_initial_state()
        o = base.officer("xun_yu")
        s = replace(
            base,
            officers={**base.officers, "xun_yu": replace(o, faction_id="faction_2", city_id="luoyang", loyalty=10, ambition=80)},
        )

        class DefectRNG(random.Random):
            def random(self):
                return 0.001

        captured_views = []

        class ViewSavingAgent(FactionAgent):
            def decide(self, view):
                captured_views.append(view)
                return FactionPlan()

        g = Game(s, {"faction_2": ViewSavingAgent()}, DefectRNG(42))
        g.step()  # turn 1: xun_yu defects
        self.assertEqual(len(g.incidents), 1)
        self.assertEqual(len(g.events), g.stats["decisions"])
        self.assertTrue(all(e.action != "defect" for e in g.events))

        # Step turn 2: view must contain the defect incident from turn 1
        g.step()
        self.assertGreater(len(captured_views), 1)
        t2_view = captured_views[1]
        self.assertTrue(
            any("defect" in ev_str for ev_str in t2_view.events),
            f"Turn 2 view events should contain defect incident, got: {t2_view.events}",
        )

    def test_forced_cast_petition_ordering_and_truncation(self):
        # forced_cast includes:
        # 1. siege/capture officers (sorted by officer_id)
        # 2. petition officers (neglect >= 4 and loyalty < 80, sorted by (-neglect, officer_id))
        # 3. truncated to CAST_LIMIT = 6
        base = build_initial_state()
        # Create siege event targeting chenliu (officers: cao_ren, li_dian)
        ev_siege = ResolutionEvent(turn=1, officer_id="guan_yu", faction_id="faction_2", action="siege", city_id="chenliu")
        # Now set petition officers in faction_1:
        # xun_yu: neglect=5, loyalty=70
        # guo_jia: neglect=6, loyalty=75
        # dian_wei: neglect=6, loyalty=60
        # jia_xu: neglect=4, loyalty=79
        # yue_jin: neglect=7, loyalty=70
        # cheng_yu: neglect=8, loyalty=70
        new_officers = dict(base.officers)
        new_officers["xun_yu"] = replace(new_officers["xun_yu"], neglect=5, loyalty=70)
        new_officers["guo_jia"] = replace(new_officers["guo_jia"], neglect=6, loyalty=75)
        new_officers["dian_wei"] = replace(new_officers["dian_wei"], neglect=6, loyalty=60)
        new_officers["jia_xu"] = replace(new_officers["jia_xu"], neglect=4, loyalty=79)
        new_officers["yue_jin"] = replace(new_officers["yue_jin"], neglect=7, loyalty=70)
        new_officers["cheng_yu"] = replace(new_officers["cheng_yu"], neglect=8, loyalty=70)
        s = replace(base, officers=new_officers)

        fc = forced_cast(s, "faction_1", [ev_siege])
        # Siege officers in chenliu: cao_ren, li_dian (2 officers)
        # Remaining slots: 6 - 2 = 4 slots
        # Petition officers by (-neglect, officer_id):
        # neglect 8: cheng_yu
        # neglect 7: yue_jin
        # neglect 6: dian_wei, guo_jia
        # neglect 5: xun_yu
        # neglect 4: jia_xu
        # Expected top 4: cheng_yu, yue_jin, dian_wei, guo_jia
        expected = ("cao_ren", "li_dian", "cheng_yu", "yue_jin", "dian_wei", "guo_jia")
        self.assertEqual(fc, expected)
        self.assertEqual(len(fc), CAST_LIMIT)

    def test_view_cast_contains_neglect_field(self):
        state = build_initial_state()
        view = build_faction_view(state, "faction_1", cast_ids=("xun_yu", "xiahou_dun"))
        self.assertGreater(len(view.cast), 0)
        for c in view.cast:
            self.assertIn("neglect", c)
            self.assertIsInstance(c["neglect"], int)

    def test_system_prompt_does_not_contain_scenario_names(self):
        state = build_initial_state()
        forbidden = set()
        for cid, city in state.cities.items():
            forbidden.add(cid)
            forbidden.add(city.name)
        for oid, officer in state.officers.items():
            forbidden.add(oid)
            forbidden.add(officer.name)
        for fid, faction in state.factions.items():
            forbidden.add(fid)
            forbidden.add(faction.name)

        for entity in forbidden:
            self.assertNotIn(entity, SYSTEM_PROMPT)


    def test_loyalty_floor_at_zero(self):
        # Loyalty penalty cannot drop loyalty below 0.
        # Put xun_yu in chenliu (which only borders xuchang, also owned by faction_1) so no defection occurs.
        officer = self.state.officer("xun_yu")
        s = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, city_id="chenliu", loyalty=1, neglect=4)},
        )
        game = Game(s, {"faction_1": ScriptedFactionAgent(orders=())}, random.Random(42))
        game.step()
        # neglect=5, penalty=5-4+1=2 -> loyalty=0
        self.assertEqual(game.state.officer("xun_yu").loyalty, 0)
        game.step()
        # neglect=6, penalty=3 -> loyalty still 0 (cannot be negative)
        self.assertEqual(game.state.officer("xun_yu").loyalty, 0)

    def test_disobey_cap_at_half(self):
        # When p formula evaluates > 0.5, it must be capped at 0.5
        # loyalty=0, ambition=100 -> (50 - 0)/100 * (0.5 + 100/100) = 0.5 * 1.5 = 0.75 -> capped at 0.50
        officer = self.state.officer("xun_yu")
        s = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=0, ambition=100)},
        )

        class RollOverCapRNG(random.Random):
            def random(self):
                # 0.501 > 0.50 -> must obey because cap is 0.50
                return 0.501

        game = Game(
            s,
            {"faction_1": ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "develop_agri"),))},
            RollOverCapRNG(42),
        )
        game.step()
        self.assertEqual(game.stats["disobeyed"], 0)
        self.assertEqual(game.events[-1].action, "develop_agri")

    def test_disobey_triggers_even_when_original_action_is_rest(self):
        # "無論行動為何消耗一次 rng.random() ... 改為 rest，detail 記 '抗旨: 忠誠{loyalty} 野心{ambition} 原令{action}'"
        officer = self.state.officer("xun_yu")
        s = replace(
            self.state,
            officers={**self.state.officers, "xun_yu": replace(officer, loyalty=40, ambition=50)},
        )

        class ForceDisobeyRNG(random.Random):
            def random(self):
                return 0.01

        game = Game(
            s,
            {"faction_1": ScriptedFactionAgent(orders=(AgentDecision("xun_yu", "rest"),))},
            ForceDisobeyRNG(42),
        )
        game.step()
        self.assertEqual(game.stats["disobeyed"], 1)
        entry = [e for e in game.log_entries if e.officer_id == "xun_yu"][0]
        self.assertEqual(entry.source, "disobey")
        self.assertEqual(entry.action, "rest")
        self.assertIn("抗旨: 忠誠40 野心50 原令rest", entry.event.detail)

    def test_petition_threshold_boundaries(self):
        # Neglect must be >= NEGLECT_PETITION (4) and loyalty must be < PETITION_LOYALTY_BELOW (80)
        base = build_initial_state()
        new_officers = dict(base.officers)
        # o1: neglect=3 (< 4), loyalty=70 -> should NOT petition
        new_officers["xun_yu"] = replace(new_officers["xun_yu"], neglect=3, loyalty=70)
        # o2: neglect=4 (>= 4), loyalty=80 (not < 80) -> should NOT petition
        new_officers["guo_jia"] = replace(new_officers["guo_jia"], neglect=4, loyalty=80)
        # o3: neglect=4 (>= 4), loyalty=79 (< 80) -> SHOULD petition
        new_officers["dian_wei"] = replace(new_officers["dian_wei"], neglect=4, loyalty=79)
        s = replace(base, officers=new_officers)

        fc = forced_cast(s, "faction_1", [])
        self.assertNotIn("xun_yu", fc)
        self.assertNotIn("guo_jia", fc)
        self.assertIn("dian_wei", fc)

    def test_defection_zero_ambition_never_defects(self):
        # p = ambition/100 * (1 - loyalty/DEFECT_BELOW). If ambition = 0, p = 0 -> never defects
        base = build_initial_state()
        o = base.officer("xun_yu")
        s = replace(
            base,
            officers={**base.officers, "xun_yu": replace(o, faction_id="faction_2", city_id="luoyang", loyalty=0, ambition=0)},
        )

        class MinRollRNG(random.Random):
            def random(self):
                return 0.0001  # u > 0 -> u > p=0, so does not defect

        game = Game(s, {"faction_2": ScriptedFactionAgent()}, MinRollRNG(42))
        game.step()
        self.assertEqual(len(game.incidents), 0)


if __name__ == "__main__":
    unittest.main()
