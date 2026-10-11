"""Tests for LLM plan parameter normalization, prompt guidelines, and siege diagnostics."""

from __future__ import annotations

import json
import unittest

from slg.agents.backends import DemoCompleter, ScriptedCompleter
from slg.agents.base import FactionAgent
from slg.agents.llm_agent import (
    SYSTEM_PROMPT,
    LLMFactionAgent,
    parse_plan,
)
from slg.engine.initial_state import build_initial_state
from slg.engine.validation import validate_decision
from slg.engine.view import build_faction_view
from slg.schema import AgentDecision, FactionPlan, ResolutionEvent
from slg.sim.evaluate import (
    _compute_game_diagnostics,
    evaluate,
    generate_possible_cause_hint,
    render_markdown,
)


class TestParamNormalization(unittest.TestCase):
    # 1. 單元素陣列拆解 - move
    def test_single_element_list_move(self):
        raw = json.dumps({
            "orders": [
                {"officer": "xun_yu", "action": "move", "params": {"to": ["chenliu"]}}
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params["to"], "chenliu")
        self.assertEqual(stats.get("normalized_params"), 1)

    # 2. 單元素陣列拆解 - siege (含 to 與 troops)
    def test_single_element_list_siege(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xiahou_dun",
                    "action": "siege",
                    "params": {"to": ["luoyang"], "troops": [800]},
                }
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params["to"], "luoyang")
        self.assertEqual(plan.orders[0].params["troops"], 800)
        self.assertEqual(stats.get("normalized_params"), 1)

    # 3. 單元素陣列拆解 - recruit (非 move/siege 行動)
    def test_single_element_list_recruit(self):
        raw = json.dumps({
            "orders": [
                {"officer": "yu_jin", "action": "recruit", "params": {"troops": [500]}}
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params["troops"], 500)
        self.assertEqual(stats.get("normalized_params"), 1)

    # 4. 長度 2 陣列不動（交給引擎拒絕）
    def test_length_2_list_untouched(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "move",
                    "params": {"to": ["chenliu", "xiangyang"]},
                }
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params["to"], ["chenliu", "xiangyang"])
        self.assertEqual(stats.get("normalized_params", 0), 0)

    # 5. 長度 0 陣列不動
    def test_length_0_list_untouched(self):
        raw = json.dumps({
            "orders": [
                {"officer": "xun_yu", "action": "move", "params": {"to": []}}
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params["to"], [])
        self.assertEqual(stats.get("normalized_params", 0), 0)

    # 6-10. 'to' 鍵別名正規化（target, destination, dest, city, target_city）
    def test_alias_target(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "move", "params": {"target": "c"}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"to": "c"})

    def test_alias_destination(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "move", "params": {"destination": "c"}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"to": "c"})

    def test_alias_dest(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "move", "params": {"dest": "c"}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"to": "c"})

    def test_alias_city(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "move", "params": {"city": "c"}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"to": "c"})

    def test_alias_target_city(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "move", "params": {"target_city": "c"}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"to": "c"})

    # 11-14. 'troops' 鍵別名正規化（troop, soldiers, army, num_troops）
    def test_alias_troop(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "recruit", "params": {"troop": 600}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"troops": 600})

    def test_alias_soldiers(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "recruit", "params": {"soldiers": 600}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"troops": 600})

    def test_alias_army(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "recruit", "params": {"army": 600}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"troops": 600})

    def test_alias_num_troops(self):
        raw = json.dumps({"orders": [{"officer": "o", "action": "recruit", "params": {"num_troops": 600}}]})
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].params, {"troops": 600})

    # 15. 規範鍵與別名並存保留規範鍵並丟棄別名
    def test_canonical_key_and_alias_coexistence(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "siege",
                    "params": {
                        "to": "luoyang",
                        "target": "wancheng",
                        "troops": 800,
                        "soldiers": 500,
                    },
                }
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params, {"to": "luoyang", "troops": 800})
        self.assertEqual(stats.get("normalized_params"), 1)

    # 16. 扁平寫法收攏進 params
    def test_flat_format_gathered_into_params(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "siege",
                    "to": "luoyang",
                    "troops": 800,
                    "memo": "攻洛陽",
                }
            ]
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(plan.orders[0].params, {"to": "luoyang", "troops": 800})
        self.assertEqual(plan.orders[0].memo, "攻洛陽")
        self.assertEqual(stats.get("normalized_params"), 1)

    # 17. 已正確輸出不被改動（逐位元/欄位相等）
    def test_already_valid_output_bitwise_equal(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "siege",
                    "params": {"to": "luoyang", "troops": 800},
                    "memo": "合乎規範",
                }
            ],
            "chronicle": "史官紀事",
            "next_cast": ["xun_yu"],
        })
        stats: dict[str, int] = {}
        plan = parse_plan(raw, stats=stats)
        self.assertEqual(
            plan.orders[0],
            AgentDecision(
                officer_id="xun_yu",
                action="siege",
                params={"to": "luoyang", "troops": 800},
                memo="合乎規範",
            ),
        )
        self.assertEqual(plan.chronicle, "史官紀事")
        self.assertEqual(plan.next_cast, ("xun_yu",))
        self.assertEqual(stats.get("normalized_params", 0), 0)

    # 18. normalized_params 計數確切（一次呼叫含 2 個需正規化 order -> 2）
    def test_normalized_params_count_exact(self):
        raw_two_normalized = json.dumps({
            "orders": [
                {"officer": "o1", "action": "move", "target": "c1"},  # 扁平+別名 -> 正規化
                {"officer": "o2", "action": "recruit", "params": {"troop": [600]}},  # 別名+單元素 -> 正規化
                {"officer": "o3", "action": "rest", "params": {}},  # 無須正規化
            ]
        })
        completer = ScriptedCompleter([raw_two_normalized])
        agent = LLMFactionAgent(completer)
        state = build_initial_state()
        view = build_faction_view(state, "faction_1", cast_ids=("xun_yu", "xiahou_dun", "yu_jin"))
        plan = agent.decide(view)
        self.assertEqual(len(plan.orders), 3)
        self.assertEqual(agent.usage["normalized_params"], 2)

    # 19. 鑑別力測試：未正規化決策被 validate_decision 拒絕，正規化後通過
    def test_validate_decision_unnormalized_fails_normalized_passes(self):
        state = build_initial_state()
        officer = state.officer("xun_yu")

        # 情況 A：單元素陣列 to=["chenliu"]
        unnormalized_decision_a = AgentDecision(
            officer_id="xun_yu", action="move", params={"to": ["chenliu"]}
        )
        ok_before_a, reason_before_a = validate_decision(state, officer, unnormalized_decision_a)
        self.assertFalse(ok_before_a, "未正規化單元素陣列應被引擎拒絕")
        self.assertIn("not in choices", reason_before_a)

        raw_a = json.dumps({"orders": [{"officer": "xun_yu", "action": "move", "params": {"to": ["chenliu"]}}]})
        plan_a = parse_plan(raw_a)
        ok_after_a, reason_after_a = validate_decision(state, officer, plan_a.orders[0])
        self.assertTrue(ok_after_a, f"正規化後應通過驗證，原因：{reason_after_a}")

        # 情況 B：別名 target="luoyang", soldiers=800
        unnormalized_decision_b = AgentDecision(
            officer_id="xun_yu", action="siege", params={"target": "luoyang", "soldiers": 800}
        )
        ok_before_b, reason_before_b = validate_decision(state, officer, unnormalized_decision_b)
        self.assertFalse(ok_before_b, "未正規化別名應被引擎拒絕")
        self.assertIn("missing required param", reason_before_b)

        raw_b = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "siege",
                    "params": {"target": "luoyang", "soldiers": 800},
                }
            ]
        })
        plan_b = parse_plan(raw_b)
        ok_after_b, reason_after_b = validate_decision(state, officer, plan_b.orders[0])
        self.assertTrue(ok_after_b, f"正規化後應通過驗證，原因：{reason_after_b}")

    # 20. SYSTEM_PROMPT 含佔位符與不可為陣列，且逐一比對不含任何城名/武將名
    def test_system_prompt_placeholders_and_entities(self):
        self.assertIn("<city_id>", SYSTEM_PROMPT)
        self.assertIn("不可為陣列", SYSTEM_PROMPT)
        self.assertIn("troops 與 defense", SYSTEM_PROMPT)

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
            self.assertNotIn(
                entity,
                SYSTEM_PROMPT,
                f"SYSTEM_PROMPT 不得包含遊戲具體實體名稱：{entity}",
            )

    # 21. siege_outcomes 診斷指標確切計算
    def test_siege_outcomes_diagnostics_exact_calculation(self):
        class MockGameResult:
            def __init__(self, events):
                self.events = events
                self.incidents = ()
                self.stats = {}
                self.final_state = build_initial_state()
                self.log = None

        events = [
            # 席位 faction_2 攻城成功 (captured_city 不為 None)
            ResolutionEvent(1, "o1", "faction_2", "siege", "c1", "captured", captured_city="c1"),
            # 席位 faction_2 攻城失敗 (captured_city 為 None)
            ResolutionEvent(1, "o2", "faction_2", "siege", "c2", "repelled", captured_city=None),
            # 席位 faction_2 其他行動
            ResolutionEvent(1, "o3", "faction_2", "recruit", "c1", "recruited"),
            # 其他勢力攻城 (不應計入 faction_2)
            ResolutionEvent(1, "o4", "faction_1", "siege", "c3", "captured", captured_city="c3"),
        ]
        res = MockGameResult(events)
        diag = _compute_game_diagnostics(res, build_initial_state(), seat="faction_2")
        self.assertIn("siege_outcomes", diag)
        so = diag["siege_outcomes"]
        self.assertEqual(so["attempts"], 2)
        self.assertEqual(so["captured"], 1)
        self.assertEqual(so["repelled"], 1)

    # 22. 提示規則：兵力 < 80% 構造觸發
    def test_possible_cause_hint_low_troops_trigger(self):
        summary = {
            "orders_accept_rate": 0.95,
            "baseline_troops": 10000,
            "experiment_troops": 7000,  # 7000 < 8000 -> -30%
            "diagnostics": {
                "action_counts": {
                    "baseline": {"recruit": 10},
                    "experiment": {"recruit": 10},
                },
                "incidents": {"experiment": {"deflections": 0}},
                "rejection_reasons": [],
                "siege_outcomes": {
                    "experiment": {"attempts": 5, "captured": 2, "repelled": 3}
                },
            },
        }
        hint = generate_possible_cause_hint(summary)
        self.assertIn("最終兵力明顯低於基準線（-30%），檢查出征損失（siege 成功率 2/5）與徵兵", hint)

    # 23. 提示規則：兵力 >= 80% 構造不觸發
    def test_possible_cause_hint_low_troops_not_trigger(self):
        summary = {
            "orders_accept_rate": 0.95,
            "baseline_troops": 10000,
            "experiment_troops": 8500,  # 8500 >= 8000
            "diagnostics": {
                "action_counts": {
                    "baseline": {"recruit": 10},
                    "experiment": {"recruit": 10},
                },
                "incidents": {"experiment": {"deflections": 0}},
                "rejection_reasons": [],
                "siege_outcomes": {
                    "experiment": {"attempts": 5, "captured": 2, "repelled": 3}
                },
            },
        }
        hint = generate_possible_cause_hint(summary)
        self.assertNotIn("最終兵力明顯低於基準線", hint)

    # 24. render_markdown 包含 siege 表
    def test_render_markdown_contains_siege_table(self):
        mock_result = {
            "aborted": False,
            "summary": {
                "seat": "faction_2",
                "seeds": [0],
                "planned_seeds": [0],
                "baseline_win_rate": 0.0,
                "experiment_win_rate": 1.0,
                "win_rate_delta": 1.0,
                "mean_cities_delta": 1.0,
                "mean_troops_delta": 500.0,
                "orders_accept_rate": 1.0,
                "plan_failure_rate": 0.0,
                "delegated_per_turn": 0.0,
                "calls": 1,
                "est_tokens": 100,
                "parse_failures": 0,
                "errors": 0,
                "diagnostics": {
                    "action_counts": {"baseline": {}, "experiment": {}},
                    "incidents": {"baseline": {}, "experiment": {}},
                    "rejection_reasons": [],
                    "named_per_turn": {},
                    "siege_outcomes": {
                        "baseline": {"attempts": 1, "captured": 0, "repelled": 1},
                        "experiment": {"attempts": 3, "captured": 2, "repelled": 1},
                    },
                },
            },
            "budget": {"max_calls": 10, "calls_used": 1, "stopped_early": False},
            "per_seed": [],
        }
        md = render_markdown(mock_result)
        self.assertIn("### 攻城勝敗 (出征 / siege_outcomes)", md)
        self.assertIn("| 攻城嘗試 (siege attempts) | 1 | 3 | +2 |", md)
        self.assertIn("| 成功攻克 (captured) | 0 | 2 | +2 |", md)
        self.assertIn("| 擊退受挫 (repelled) | 1 | 1 | +0 |", md)

    # 25. usage 新欄位不破壞 evaluate 加總
    def test_usage_new_field_does_not_break_evaluate(self):
        res = evaluate(
            seeds=[0],
            turns=2,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
        )
        self.assertIn("summary", res)
        summary = res["summary"]
        self.assertIn("normalized_params", summary)
        self.assertIsInstance(summary["normalized_params"], int)
        self.assertIsInstance(summary["calls"], int)
        self.assertIsInstance(summary["est_tokens"], int)
        self.assertIsInstance(summary["parse_failures"], int)
        self.assertIsInstance(summary["errors"], int)
        self.assertIn("siege_outcomes", summary["diagnostics"])


if __name__ == "__main__":
    unittest.main()
