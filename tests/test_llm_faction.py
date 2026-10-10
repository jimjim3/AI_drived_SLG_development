import json
import unittest

from slg.agents.base import AgentError
from slg.agents.backends import ScriptedCompleter
from slg.agents.llm_agent import (
    SYSTEM_PROMPT,
    LLMFactionAgent,
    PlanParseError,
    build_user_prompt,
    parse_plan,
)
from slg.engine.initial_state import build_initial_state
from slg.engine.view import build_faction_view
from slg.schema import CHRONICLE_MAX, MEMO_MAX


class LLMFactionAgentTests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()
        self.view = build_faction_view(self.state, "faction_1", cast_ids=("xun_yu",))

    def test_system_prompt_contains_no_game_specific_entities(self):
        # SYSTEM_PROMPT must be fixed and cacheable across scenarios and turns.
        # It must not mention any scenario city or officer names/IDs.
        forbidden = set()
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

    def test_build_user_prompt_without_error(self):
        prompt = build_user_prompt(self.view, error=None)
        self.assertTrue(prompt.startswith("狀態："))
        self.assertNotIn("上次輸出無法使用", prompt)
        # Check that JSON payload is valid
        data = json.loads(prompt[len("狀態：") :])
        self.assertEqual(data["faction_id"], "faction_1")

    def test_build_user_prompt_with_error(self):
        error_msg = "Order #0 missing action field"
        prompt = build_user_prompt(self.view, error=error_msg)
        self.assertTrue(prompt.startswith("狀態："))
        expected_suffix = f"\n上次輸出無法使用：{error_msg}。請只輸出修正後的 JSON。"
        self.assertTrue(prompt.endswith(expected_suffix))

    def test_parse_plan_valid(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "develop_agri",
                    "params": {},
                    "memo": "勸課農桑",
                }
            ],
            "chronicle": "許昌大治，府庫充盈。",
            "next_cast": ["xun_yu", "xiahou_dun"],
        })
        plan = parse_plan(raw)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(plan.orders[0].officer_id, "xun_yu")
        self.assertEqual(plan.orders[0].action, "develop_agri")
        self.assertEqual(plan.orders[0].params, {})
        self.assertEqual(plan.orders[0].memo, "勸課農桑")
        self.assertEqual(plan.chronicle, "許昌大治，府庫充盈。")
        self.assertEqual(plan.next_cast, ("xun_yu", "xiahou_dun"))

    def test_parse_plan_with_markdown_fences(self):
        inner = json.dumps({"orders": [], "chronicle": "休養生息", "next_cast": []})
        raw = f"```json\n{inner}\n```"
        plan = parse_plan(raw)
        self.assertEqual(plan.chronicle, "休養生息")

    def test_parse_plan_with_surrounding_text(self):
        inner = json.dumps({"orders": [], "chronicle": "平靜無事"})
        raw = f"主公，這是本月策劃：\n{inner}\n望主公明察！"
        plan = parse_plan(raw)
        self.assertEqual(plan.chronicle, "平靜無事")

    def test_parse_plan_empty_orders_and_defaults(self):
        raw = "{}"
        plan = parse_plan(raw)
        self.assertEqual(plan.orders, ())
        self.assertEqual(plan.chronicle, "")
        self.assertEqual(plan.next_cast, ())

    def test_parse_plan_officer_id_fallback_key(self):
        raw = json.dumps({"orders": [{"officer_id": "cao_ren", "action": "rest"}]})
        plan = parse_plan(raw)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(plan.orders[0].officer_id, "cao_ren")

    def test_parse_plan_missing_officer_raises(self):
        raw = json.dumps({"orders": [{"action": "rest"}]})
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("officer", str(cm.exception))

    def test_parse_plan_missing_action_raises(self):
        raw = json.dumps({"orders": [{"officer": "xun_yu"}]})
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("action", str(cm.exception))

    def test_parse_plan_orders_not_list_raises(self):
        raw = json.dumps({"orders": "invalid_string"})
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("orders", str(cm.exception))

    def test_parse_plan_params_not_dict_raises(self):
        raw = json.dumps({"orders": [{"officer": "xun_yu", "action": "recruit", "params": 500}]})
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("params", str(cm.exception))

    def test_parse_plan_memo_truncated_to_max(self):
        long_memo = "a" * (MEMO_MAX + 15)
        raw = json.dumps({"orders": [{"officer": "xun_yu", "action": "rest", "memo": long_memo}]})
        plan = parse_plan(raw)
        self.assertEqual(len(plan.orders[0].memo), MEMO_MAX)
        self.assertEqual(plan.orders[0].memo, long_memo[:MEMO_MAX])

    def test_parse_plan_chronicle_truncated_to_max(self):
        long_chronicle = "記" * (CHRONICLE_MAX + 50)
        raw = json.dumps({"chronicle": long_chronicle})
        plan = parse_plan(raw)
        self.assertEqual(len(plan.chronicle), CHRONICLE_MAX)
        self.assertEqual(plan.chronicle, long_chronicle[:CHRONICLE_MAX])

    def test_parse_plan_float_converted_to_int(self):
        raw = json.dumps({
            "orders": [
                {
                    "officer": "xun_yu",
                    "action": "recruit",
                    "params": {"troops": 500.0, "ratio": 1.5},
                }
            ]
        })
        plan = parse_plan(raw)
        params = plan.orders[0].params
        self.assertIsInstance(params["troops"], int)
        self.assertEqual(params["troops"], 500)
        self.assertIsInstance(params["ratio"], float)
        self.assertEqual(params["ratio"], 1.5)

    def test_parse_plan_unknown_action_and_officer_allowed(self):
        # Plan parsing does not check game rules; engine validates decisions.
        raw = json.dumps({
            "orders": [{"officer": "unknown_ghost", "action": "super_spell", "params": {}}]
        })
        plan = parse_plan(raw)
        self.assertEqual(plan.orders[0].officer_id, "unknown_ghost")
        self.assertEqual(plan.orders[0].action, "super_spell")

    def test_parse_plan_next_cast_truncated_to_12(self):
        raw = json.dumps({"next_cast": [f"off_{i}" for i in range(20)]})
        plan = parse_plan(raw)
        self.assertEqual(len(plan.next_cast), 12)
        self.assertEqual(plan.next_cast, tuple(f"off_{i}" for i in range(12)))

    def test_parse_plan_next_cast_invalid_type_raises(self):
        raw = json.dumps({"next_cast": ["valid_id", 12345]})
        with self.assertRaises(PlanParseError) as cm:
            parse_plan(raw)
        self.assertIn("next_cast", str(cm.exception))

    def test_llm_agent_success_on_first_try(self):
        valid_json = json.dumps({"orders": [{"officer": "xun_yu", "action": "rest"}]})
        completer = ScriptedCompleter([valid_json])
        agent = LLMFactionAgent(completer, max_retries=1)

        plan = agent.decide(self.view)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(agent.usage["calls"], 1)
        self.assertEqual(agent.usage["parse_failures"], 0)
        self.assertEqual(agent.usage["errors"], 0)
        self.assertGreater(agent.usage["prompt_chars"], 0)
        self.assertGreater(agent.usage["response_chars"], 0)

    def test_llm_agent_retry_on_garbage_then_success(self):
        garbage = "I am a helpful assistant who forgot JSON."
        valid_json = json.dumps({"orders": [{"officer": "xun_yu", "action": "rest"}]})
        completer = ScriptedCompleter([garbage, valid_json])
        agent = LLMFactionAgent(completer, max_retries=1)

        plan = agent.decide(self.view)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(agent.usage["calls"], 2)
        self.assertEqual(agent.usage["parse_failures"], 1)
        self.assertEqual(agent.usage["errors"], 0)

        # Verify that the second call received the error feedback in user prompt
        second_call_user_prompt = completer.calls[1][1]
        self.assertIn("上次輸出無法使用：", second_call_user_prompt)
        self.assertIn("未找到 JSON 物件", second_call_user_prompt)

    def test_llm_agent_retry_on_completer_exception_then_success(self):
        valid_json = json.dumps({"orders": [{"officer": "xun_yu", "action": "rest"}]})
        completer = ScriptedCompleter([RuntimeError("upstream timeout"), valid_json])
        agent = LLMFactionAgent(completer, max_retries=1)

        plan = agent.decide(self.view)
        self.assertEqual(len(plan.orders), 1)
        self.assertEqual(agent.usage["calls"], 2)
        self.assertEqual(agent.usage["errors"], 1)
        self.assertEqual(agent.usage["parse_failures"], 0)

        # Verify error message appeared in second prompt
        second_call_user_prompt = completer.calls[1][1]
        self.assertIn("upstream timeout", second_call_user_prompt)

    def test_llm_agent_all_retries_fail_raises_agent_error(self):
        completer = ScriptedCompleter(["bad 1", "bad 2"])
        agent = LLMFactionAgent(completer, max_retries=1)

        with self.assertRaises(AgentError) as cm:
            agent.decide(self.view)
        self.assertEqual(agent.usage["calls"], 2)
        self.assertEqual(agent.usage["parse_failures"], 2)
        self.assertIn("未找到 JSON 物件", str(cm.exception))

    def test_llm_agent_max_retries_zero_does_not_retry(self):
        completer = ScriptedCompleter(["bad output", "unused output"])
        agent = LLMFactionAgent(completer, max_retries=0)

        with self.assertRaises(AgentError):
            agent.decide(self.view)
        self.assertEqual(agent.usage["calls"], 1)


if __name__ == "__main__":
    unittest.main()
