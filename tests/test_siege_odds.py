"""Tests for first JSON object parsing, siege odds estimation, view integration, and prompt guidance."""

from __future__ import annotations

from dataclasses import replace
import json
import math
import random
import unittest
from unittest.mock import patch

from slg.agents.llm_agent import SYSTEM_PROMPT, PlanParseError, parse_plan
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import NO_OFFICER_DEFENSE_SKILL, _resolve_siege, estimate_siege_ratio
from slg.engine.view import build_faction_view
from slg.schema import AgentDecision


class ConstantRNG(random.Random):
    """RNG subclass where uniform always returns 1.0 for deterministic combat verification."""

    def uniform(self, a: float, b: float) -> float:
        return 1.0


class TestParsePlanFirstObject(unittest.TestCase):
    """Tests for parse_plan taking only the first complete JSON object and ignoring trailing text/objects."""

    def test_parse_plan_two_json_objects_takes_first_only(self):
        # Discriminative test: two JSON objects. The second object must be ignored and not leak into the result.
        raw = (
            '{"orders":[{"officer":"xun_yu","action":"rest","memo":"第一條"}],"chronicle":"首段史官","next_cast":["xun_yu"]}'
            ' {"orders":[{"officer":"xiahou_dun","action":"move","params":{"to":"chenliu"}}],"chronicle":"第二段","next_cast":["xiahou_dun"]}'
        )
        plan = parse_plan(raw)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(plan.orders[0].officer_id, "xun_yu")
        self.assertEqual(plan.orders[0].action, "rest")
        self.assertEqual(plan.orders[0].memo, "第一條")
        self.assertEqual(plan.chronicle, "首段史官")
        self.assertEqual(plan.next_cast, ("xun_yu",))

        # Assert second object contents did not contaminate plan
        self.assertNotIn("xiahou_dun", [o.officer_id for o in plan.orders])
        self.assertNotIn("第二段", plan.chronicle)
        self.assertNotIn("xiahou_dun", plan.next_cast)

    def test_parse_plan_json_followed_by_explanation_text(self):
        # Discriminative test: valid JSON followed by trailing natural language notes.
        raw = (
            '{"orders":[{"officer":"xun_yu","action":"rest"}],"chronicle":"靜候時機"}\n'
            "【額外說明】本回合曹操軍休養生息，切勿躁進。請主公斟酌！"
        )
        plan = parse_plan(raw)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(plan.orders[0].officer_id, "xun_yu")
        self.assertEqual(plan.chronicle, "靜候時機")

    def test_parse_plan_code_fence_followed_by_second_fence(self):
        # Discriminative test: code fence followed by a second fence.
        raw = (
            '```json\n{"orders":[{"officer":"xun_yu","action":"rest"}],"chronicle":"圍欄一"}\n```\n'
            '```json\n{"orders":[{"officer":"xiahou_dun","action":"rest"}],"chronicle":"圍欄二"}\n```'
        )
        plan = parse_plan(raw)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(plan.orders[0].officer_id, "xun_yu")
        self.assertEqual(plan.chronicle, "圍欄一")
        self.assertNotIn("圍欄二", plan.chronicle)

    def test_parse_plan_first_object_syntax_error_raises_parse_error(self):
        # Syntax error in the first object must still raise PlanParseError with specific message
        raw = '{"orders": [} {"orders": []}'
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("JSON 語法錯誤", str(cm.exception))

    def test_parse_plan_top_level_non_dict_raises_parse_error(self):
        # Top-level array instead of dict must raise PlanParseError
        raw = '[{"orders": []}]'
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("頂層必須為 dict", str(cm.exception))

    def test_parse_plan_no_json_object_raises_parse_error(self):
        # No JSON object at all must raise PlanParseError
        raw = "主公，這是一段沒有 JSON 的對話回應。"
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("未找到 JSON 物件", str(cm.exception))


class TestEstimateSiegeRatio(unittest.TestCase):
    """Tests for estimate_siege_ratio consistency with _resolve_siege and hand-calculated values."""

    def setUp(self):
        self.base_state = build_initial_state()
        self.rng = ConstantRNG()

    def test_estimate_siege_ratio_hand_calculated_defeat_group_1(self):
        # Group 1: Attacker defeat (ratio < 1.0)
        # Attacker: war=60, lea=80, troops=1000 -> atk_base = 1000 * (0.5 + 140/200) = 1200.0
        # Target: luoyang, troops=1200, def=100
        # Defender in luoyang: zhuge_liang war=70, lea=50 -> dq = 60.0
        # dfn_base = 1200 * (1 + 100/200) * (0.5 + 60/100) = 1200 * 1.5 * 1.1 = 1980.0
        # Expected ratio = 1200 / 1980 = 20 / 33 = 0.6060606060606061
        s = self.base_state
        o_atk = replace(s.officer("xun_yu"), war=60, leadership=80)
        c_tgt = replace(s.city("luoyang"), troops=1200, defense=100)
        o_def = replace(s.officer("zhuge_liang"), war=70, leadership=50, city_id="luoyang")

        new_officers = dict(s.officers)
        for oid, o in s.officers.items():
            if o.city_id == "luoyang" and oid != "zhuge_liang":
                new_officers[oid] = replace(o, city_id="chengdu")
        new_officers["xun_yu"] = o_atk
        new_officers["zhuge_liang"] = o_def
        new_cities = dict(s.cities)
        new_cities["luoyang"] = c_tgt
        s = replace(s, officers=new_officers, cities=new_cities)

        troops = 1000
        ratio = estimate_siege_ratio(s, o_atk, "luoyang", troops)
        expected_ratio = 1200.0 / 1980.0
        self.assertAlmostEqual(ratio, expected_ratio, places=9)
        self.assertLess(ratio, 1.0)

        # Consistency with _resolve_siege when rng.uniform == 1.0
        dec = AgentDecision(officer_id="xun_yu", action="siege", params={"to": "luoyang", "troops": troops})
        _, ev = _resolve_siege(s, o_atk, dec, self.rng)
        self.assertIn("repelled at", ev.detail)
        self.assertIsNone(ev.captured_city)

    def test_estimate_siege_ratio_hand_calculated_victory_group_2(self):
        # Group 2: Attacker victory (ratio > 1.0)
        # Attacker: war=90, lea=90, troops=2000 -> atk_base = 2000 * (0.5 + 180/200) = 2800.0
        # Target: luoyang, troops=800, def=40
        # Defender in luoyang: zhuge_liang war=60, lea=60 -> dq = 60.0
        # dfn_base = 800 * (1 + 40/200) * (0.5 + 60/100) = 800 * 1.2 * 1.1 = 1056.0
        # Expected ratio = 2800 / 1056 = 175 / 66 = 2.6515151515151514
        s = self.base_state
        o_atk = replace(s.officer("xiahou_dun"), war=90, leadership=90)
        c_tgt = replace(s.city("luoyang"), troops=800, defense=40)
        o_def = replace(s.officer("zhuge_liang"), war=60, leadership=60, city_id="luoyang")

        new_officers = dict(s.officers)
        for oid, o in s.officers.items():
            if o.city_id == "luoyang" and oid != "zhuge_liang":
                new_officers[oid] = replace(o, city_id="chengdu")
        new_officers["xiahou_dun"] = o_atk
        new_officers["zhuge_liang"] = o_def
        new_cities = dict(s.cities)
        new_cities["luoyang"] = c_tgt
        s = replace(s, officers=new_officers, cities=new_cities)

        troops = 2000
        ratio = estimate_siege_ratio(s, o_atk, "luoyang", troops)
        expected_ratio = 2800.0 / 1056.0
        self.assertAlmostEqual(ratio, expected_ratio, places=9)
        self.assertGreater(ratio, 1.0)

        # Consistency with _resolve_siege when rng.uniform == 1.0
        dec = AgentDecision(officer_id="xiahou_dun", action="siege", params={"to": "luoyang", "troops": troops})
        _, ev = _resolve_siege(s, o_atk, dec, self.rng)
        self.assertIn("captured", ev.detail)
        self.assertEqual(ev.captured_city, "luoyang")

    def test_estimate_siege_ratio_hand_calculated_no_defenders_group_3(self):
        # Group 3: No living defending officers in target city (dq = NO_OFFICER_DEFENSE_SKILL = 40)
        # Attacker: war=70, lea=70, troops=1500 -> atk_base = 1500 * (0.5 + 140/200) = 1800.0
        # Target: luoyang, troops=1000, def=60
        # Defenders in luoyang: none (dq = 40.0)
        # dfn_base = 1000 * (1 + 60/200) * (0.5 + 40/100) = 1000 * 1.3 * 0.9 = 1170.0
        # Expected ratio = 1800 / 1170 = 20 / 13 = 1.5384615384615385
        s = self.base_state
        o_atk = replace(s.officer("xun_yu"), war=70, leadership=70)
        c_tgt = replace(s.city("luoyang"), troops=1000, defense=60)

        new_officers = dict(s.officers)
        for oid, o in s.officers.items():
            if o.city_id == "luoyang":
                new_officers[oid] = replace(o, city_id="chengdu")
        new_officers["xun_yu"] = o_atk
        new_cities = dict(s.cities)
        new_cities["luoyang"] = c_tgt
        s = replace(s, officers=new_officers, cities=new_cities)

        troops = 1500
        ratio = estimate_siege_ratio(s, o_atk, "luoyang", troops)
        expected_ratio = 1800.0 / 1170.0
        self.assertAlmostEqual(ratio, expected_ratio, places=9)
        self.assertGreater(ratio, 1.0)

        # Consistency with _resolve_siege when rng.uniform == 1.0
        dec = AgentDecision(officer_id="xun_yu", action="siege", params={"to": "luoyang", "troops": troops})
        _, ev = _resolve_siege(s, o_atk, dec, self.rng)
        self.assertIn("captured", ev.detail)
        self.assertEqual(ev.captured_city, "luoyang")

    def test_estimate_siege_ratio_hand_calculated_tie_group_4(self):
        # Group 4: Exact tie atk_base == dfn_base -> ratio == 1.0 (repelled, as victory requires atk > dfn)
        # Attacker: war=50, lea=50, troops=1000 -> atk_base = 1000 * (0.5 + 100/200) = 1000.0
        # Target: luoyang, troops=1000, def=0, def officer war=50, lea=50 (dq=50) -> dfn_base = 1000.0
        s = self.base_state
        o_atk = replace(s.officer("xun_yu"), war=50, leadership=50)
        c_tgt = replace(s.city("luoyang"), troops=1000, defense=0)
        o_def = replace(s.officer("zhuge_liang"), war=50, leadership=50, city_id="luoyang")

        new_officers = dict(s.officers)
        for oid, o in s.officers.items():
            if o.city_id == "luoyang" and oid != "zhuge_liang":
                new_officers[oid] = replace(o, city_id="chengdu")
        new_officers["xun_yu"] = o_atk
        new_officers["zhuge_liang"] = o_def
        new_cities = dict(s.cities)
        new_cities["luoyang"] = c_tgt
        s = replace(s, officers=new_officers, cities=new_cities)

        troops = 1000
        ratio = estimate_siege_ratio(s, o_atk, "luoyang", troops)
        self.assertEqual(ratio, 1.0)
        self.assertFalse(ratio > 1.0)

        # In _resolve_siege, atk (1000) > dfn (1000) is False -> repelled
        dec = AgentDecision(officer_id="xun_yu", action="siege", params={"to": "luoyang", "troops": troops})
        _, ev = _resolve_siege(s, o_atk, dec, self.rng)
        self.assertIn("repelled at", ev.detail)

    def test_estimate_siege_ratio_inf_scenario_when_defender_zero_troops(self):
        # Target city has 0 troops -> dfn_base <= 0 -> returns float("inf")
        s = self.base_state
        c_tgt = replace(s.city("luoyang"), troops=0)
        cities = dict(s.cities)
        cities["luoyang"] = c_tgt
        s = replace(s, cities=cities)

        ratio = estimate_siege_ratio(s, s.officer("xun_yu"), "luoyang", 1000)
        self.assertTrue(math.isinf(ratio))
        self.assertGreater(ratio, 0.0)

    def test_estimate_siege_ratio_inf_scenario_when_dfn_base_non_positive(self):
        # When defender city has 0 troops or negative dfn_base, estimate_siege_ratio returns inf
        s = self.base_state
        c_tgt = replace(s.city("luoyang"), troops=0, defense=0)
        cities = dict(s.cities)
        cities["luoyang"] = c_tgt
        s = replace(s, cities=cities)

        ratio = estimate_siege_ratio(s, s.officer("xiahou_dun"), "luoyang", 500)
        self.assertEqual(ratio, float("inf"))


class TestViewSiegeOdds(unittest.TestCase):
    """Tests for FactionView.cast siege_odds scout report integration."""

    def setUp(self):
        self.state = build_initial_state()

    def test_view_cast_siege_odds_present_when_siege_is_legal(self):
        # Officer xun_yu in xuchang has legal siege against luoyang in initial state
        view = build_faction_view(self.state, "faction_1", cast_ids=["xun_yu"])
        xun_yu_cast = next(c for c in view.cast if c["id"] == "xun_yu")
        self.assertIn("siege_odds", xun_yu_cast)
        self.assertIsInstance(xun_yu_cast["siege_odds"], dict)

    def test_view_cast_siege_odds_keys_equal_legal_targets(self):
        # The key set of siege_odds must exactly equal the legal targets in legal actions
        o = self.state.officer("xun_yu")
        legal_actions = generate_legal_actions(self.state, o)
        siege_la = next(la for la in legal_actions if la.action == "siege")
        expected_targets = set(siege_la.params["to"].choices or ())

        view = build_faction_view(self.state, "faction_1", cast_ids=["xun_yu"])
        xun_yu_cast = next(c for c in view.cast if c["id"] == "xun_yu")
        self.assertEqual(set(xun_yu_cast["siege_odds"].keys()), expected_targets)

    def test_view_cast_siege_odds_absent_when_no_legal_siege(self):
        # cao_ren in chenliu has no adjacent enemy cities -> no legal siege action
        view = build_faction_view(self.state, "faction_1", cast_ids=["cao_ren"])
        cao_ren_cast = next(c for c in view.cast if c["id"] == "cao_ren")
        self.assertNotIn("siege_odds", cao_ren_cast)

    def test_view_cast_siege_odds_values_match_rounded_estimate(self):
        # Every value in siege_odds must match estimate_siege_ratio(max_troops) rounded to 2 decimal places
        o = self.state.officer("xiahou_dun")
        legal_actions = generate_legal_actions(self.state, o)
        siege_la = next(la for la in legal_actions if la.action == "siege")
        max_troops = int(siege_la.params["troops"].max)

        view = build_faction_view(self.state, "faction_1", cast_ids=["xiahou_dun"])
        xiahou_cast = next(c for c in view.cast if c["id"] == "xiahou_dun")

        for target_id, odds in xiahou_cast["siege_odds"].items():
            expected = round(estimate_siege_ratio(self.state, o, target_id, max_troops), 2)
            self.assertEqual(odds, expected)

    def test_view_cast_siege_odds_inf_replaced_with_99(self):
        # When defender city has 0 troops (infinite ratio), siege_odds replaces inf with 99.0
        s = self.state
        luoyang = replace(s.city("luoyang"), troops=0)
        cities = dict(s.cities)
        cities["luoyang"] = luoyang
        s = replace(s, cities=cities)

        view = build_faction_view(s, "faction_1", cast_ids=["xun_yu"])
        xun_yu_cast = next(c for c in view.cast if c["id"] == "xun_yu")
        self.assertEqual(xun_yu_cast["siege_odds"]["luoyang"], 99.0)

    def test_view_to_dict_json_serializable(self):
        # View must serialize to JSON string without error (no Infinity or NaN)
        view = build_faction_view(self.state, "faction_1", cast_ids=["xun_yu", "xiahou_dun", "cao_ren"])
        payload = json.dumps(view.to_dict())
        self.assertIsInstance(payload, str)
        deserialized = json.loads(payload)
        self.assertEqual(deserialized["faction_id"], "faction_1")

    def test_view_unaffected_fields_bitwise_preserved(self):
        # Verify cast standard keys and frontier fields are preserved exactly
        view = build_faction_view(self.state, "faction_1", cast_ids=["xun_yu", "cao_ren"])
        standard_cast_keys = ["id", "name", "city", "politics", "war", "leadership", "loyalty", "ambition", "neglect", "legal"]

        for cast_item in view.cast:
            for k in standard_cast_keys:
                self.assertIn(k, cast_item)
            if "siege_odds" in cast_item:
                self.assertEqual(set(cast_item.keys()), set(standard_cast_keys + ["siege_odds"]))
            else:
                self.assertEqual(set(cast_item.keys()), set(standard_cast_keys))

        for frontier_item in view.frontier:
            self.assertEqual(
                set(frontier_item.keys()),
                {"id", "name", "owner", "troops", "defense", "adjacent_to"},
            )


class TestSystemPrompt(unittest.TestCase):
    """Tests for SYSTEM_PROMPT guidance on siege_odds and absence of scenario entity names."""

    def setUp(self):
        self.state = build_initial_state()

    def test_system_prompt_contains_siege_odds_and_threshold(self):
        self.assertIn("siege_odds", SYSTEM_PROMPT)
        self.assertIn("1.3", SYSTEM_PROMPT)

    def test_system_prompt_contains_no_game_specific_entities(self):
        forbidden: set[str] = set()
        for cid, city in self.state.cities.items():
            forbidden.add(cid)
            forbidden.add(city.name)
        for oid, officer in self.state.officers.items():
            forbidden.add(oid)
            forbidden.add(officer.name)
        for fid, faction in self.state.factions.items():
            forbidden.add(fid)
            forbidden.add(faction.name)

        for entity in forbidden:
            self.assertNotIn(
                entity,
                SYSTEM_PROMPT,
                f"SYSTEM_PROMPT must not contain '{entity}'",
            )


if __name__ == "__main__":
    unittest.main()
