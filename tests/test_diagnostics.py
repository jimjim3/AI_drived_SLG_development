"""Tests for diagnostic data, API key format validation, and aborted reporting."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from slg.agents.backends import (
    BackendUnavailable,
    CircuitBreakerCompleter,
    ConfigError,
    DemoCompleter,
    OpenAIChatCompleter,
)
from slg.agents.base import FactionAgent
from slg.agents.llm_agent import LLMFactionAgent
from slg.engine.initial_state import build_initial_state
from slg.engine.view import FactionView, build_faction_view, select_cast
from slg.schema import AgentDecision, FactionPlan
from slg.sim.evaluate import (
    _compute_officer_loss_curve,
    _compute_rejection_reasons,
    evaluate,
    generate_possible_cause_hint,
    render_markdown,
)
from slg.sim.headless import run_headless


class AlwaysRestAgent(FactionAgent):
    """FactionAgent that explicitly orders all faction officers to rest."""

    name = "always_rest"

    def __init__(self, officer_ids: Sequence[str] | None = None) -> None:
        self.officer_ids = list(officer_ids) if officer_ids is not None else None

    def decide(self, view: FactionView) -> FactionPlan:
        oids = self.officer_ids if self.officer_ids is not None else [o["id"] for o in view.cast]
        orders = [
            AgentDecision(
                officer_id=oid,
                action="rest",
                params={},
                memo="全體休息",
            )
            for oid in oids
        ]
        return FactionPlan(orders=tuple(orders), chronicle="全體休息")


class NeverNamedAgent(FactionAgent):
    """FactionAgent that gives empty orders, leaving all officers to delegation."""

    name = "never_named"

    def decide(self, view: FactionView) -> FactionPlan:
        return FactionPlan(orders=(), chronicle="全體委任")


class FixedSixNamedAgent(FactionAgent):
    """FactionAgent that always names exactly 6 officers to rest."""

    name = "fixed_six_named"

    def decide(self, view: FactionView) -> FactionPlan:
        orders = []
        for officer in view.cast[:6]:
            orders.append(
                AgentDecision(
                    officer_id=officer["id"],
                    action="rest",
                    params={},
                    memo="點名休息",
                )
            )
        return FactionPlan(orders=tuple(orders), chronicle="點名六人")


class TestDiagnostics(unittest.TestCase):
    # 1. action_counts: AlwaysRestAgent produces exact count == turns * cast_size
    def test_action_counts_always_rest_agent_exact(self):
        turns = 4
        seat = "faction_2"
        init_state = build_initial_state()
        living_count = len([o for o in init_state.officers.values() if o.faction_id == seat and o.is_alive])

        seat_officer_ids = [o.officer_id for o in init_state.officers.values() if o.faction_id == seat and o.is_alive]
        res = evaluate(
            seeds=[0],
            turns=turns,
            seat=seat,
            agent_factory=lambda: AlwaysRestAgent(seat_officer_ids),
        )

        diag = res["per_seed"][0]["diagnostics"]
        self.assertIn("action_counts", diag)
        self.assertIn("baseline", diag["action_counts"])
        self.assertIn("experiment", diag["action_counts"])

        # When all officers are ordered to rest, exactly turns * living_count rest actions occur
        expected_rest_count = turns * living_count
        exp_rest = diag["action_counts"]["experiment"].get("rest", 0)
        self.assertEqual(exp_rest, expected_rest_count)

        # Baseline must have non-rest actions like recruit / farm / train
        base_actions = diag["action_counts"]["baseline"]
        self.assertGreater(len(base_actions), 1)

    # 2. action_counts: DemoCompleter counts match actual Game.events
    def test_action_counts_demo_completer_matches_events(self):
        seat = "faction_2"
        res = evaluate(
            seeds=[1],
            turns=3,
            seat=seat,
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
        )

        diag = res["per_seed"][0]["diagnostics"]
        summary_diag = res["summary"]["diagnostics"]

        self.assertIn("action_counts", diag)
        self.assertIn("action_counts", summary_diag)

        # Sum of action counts must equal total actions recorded for that faction
        exp_counts = diag["action_counts"]["experiment"]
        self.assertGreater(sum(exp_counts.values()), 0)
        self.assertEqual(
            diag["action_counts"]["experiment"],
            summary_diag["action_counts"]["experiment"],
        )

    # 3. named_per_turn: NeverNamedAgent produces named == 0.0, delegated == num_officers
    def test_named_per_turn_never_named(self):
        seat = "faction_2"
        init_state = build_initial_state()
        living_count = len([o for o in init_state.officers.values() if o.faction_id == seat and o.is_alive])

        res = evaluate(
            seeds=[0],
            turns=3,
            seat=seat,
            agent_factory=lambda: NeverNamedAgent(),
        )

        npt = res["per_seed"][0]["diagnostics"]["named_per_turn"]
        self.assertEqual(npt["named"], 0.0)
        self.assertEqual(npt["delegated"], float(living_count))

    # 4. named_per_turn: FixedSixNamedAgent produces named == 6.0
    def test_named_per_turn_fixed_six_named(self):
        seat = "faction_2"
        init_state = build_initial_state()
        living_count = len([o for o in init_state.officers.values() if o.faction_id == seat and o.is_alive])

        res = evaluate(
            seeds=[0],
            turns=3,
            seat=seat,
            agent_factory=lambda: FixedSixNamedAgent(),
        )

        npt = res["per_seed"][0]["diagnostics"]["named_per_turn"]
        self.assertEqual(npt["named"], 6.0)
        self.assertEqual(npt["delegated"], float(living_count - 6))

    # 5. incidents: consistency with run_headless direct execution
    def test_incidents_consistency_with_run_headless(self):
        seed = 42
        turns = 5
        seat = "faction_2"

        direct = run_headless(seed=seed, turns=turns)
        res = evaluate(
            seeds=[seed],
            turns=turns,
            seat=seat,
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
        )

        base_inc = res["per_seed"][0]["diagnostics"]["incidents"]["baseline"]
        expected_defects = sum(
            1 for inc in direct.incidents
            if getattr(inc, "action", "") == "defect" and getattr(inc, "faction_id", "") == seat
        )
        self.assertEqual(base_inc["deflections"], expected_defects)
        self.assertEqual(base_inc["disobeyed"], 0)

        expected_init = len([o for o in build_initial_state().officers.values() if o.faction_id == seat and o.is_alive])
        expected_final = len([o for o in direct.final_state.officers.values() if o.faction_id == seat and o.is_alive])
        self.assertEqual(base_inc["initial_officers"], expected_init)
        self.assertEqual(base_inc["final_officers"], expected_final)

    # 6. officer_loss_curve: length equals actual_turns, ends at final officer count
    def test_officer_loss_curve_length_and_final_count(self):
        seat = "faction_2"
        turns = 4
        res = evaluate(
            seeds=[0],
            turns=turns,
            seat=seat,
            agent_factory=lambda: AlwaysRestAgent(),
        )

        curve = res["per_seed"][0]["diagnostics"]["officer_loss_curve"]
        self.assertIsInstance(curve, list)
        self.assertEqual(len(curve), turns)

        final_officers = res["per_seed"][0]["diagnostics"]["incidents"]["final_officers"]
        self.assertEqual(curve[-1], final_officers)

    # 7. officer_loss_curve helper calculation with mock defection events
    def test_officer_loss_curve_defection_accounting(self):
        class MockIncident:
            def __init__(self, turn: int, action: str, faction_id: str, detail: str) -> None:
                self.turn = turn
                self.action = action
                self.faction_id = faction_id
                self.detail = detail

        # Start with 6 officers. Turn 1: 1 officer defects away -> 5.
        # Turn 2: no change -> 5. Turn 3: 1 officer defects into faction_2 -> 6.
        incidents = [
            MockIncident(1, "defect", "faction_2", "出奔: faction_2 -> faction_1 (忠誠10)"),
            MockIncident(3, "defect", "faction_3", "出奔: faction_3 -> faction_2 (忠誠15)"),
        ]
        curve = _compute_officer_loss_curve(
            initial_count=6,
            actual_turns=3,
            incidents=incidents,
            seat="faction_2",
        )
        self.assertEqual(curve, [5, 5, 6])

    # 8. rejection_reasons: number normalization merges need 600, have 120 and need 800, have 50
    def test_rejection_reasons_normalization(self):
        class MockFlog:
            def __init__(self, faction_id: str, rejected: list) -> None:
                self.faction_id = faction_id
                self.rejected = rejected

        flogs = [
            MockFlog(
                "faction_2",
                [
                    ("o1", "recruit", "insufficient gold: need 600, have 120"),
                    ("o2", "recruit", "insufficient gold: need 800, have 50"),
                    ("o3", "move", "target city cid_3 not adjacent"),
                ],
            )
        ]

        top_reasons = _compute_rejection_reasons(flogs, seat="faction_2", top_n=3)
        self.assertEqual(len(top_reasons), 2)
        # Normalized reason should merge both insufficient gold messages
        self.assertEqual(top_reasons[0]["reason"], "insufficient gold: need N, have N")
        self.assertEqual(top_reasons[0]["count"], 2)
        self.assertEqual(top_reasons[1]["reason"], "target city cid_N not adjacent")
        self.assertEqual(top_reasons[1]["count"], 1)

    # 9. possible cause hint: low recruit trigger
    def test_possible_cause_hint_rule_low_recruit(self):
        summary = {
            "orders_accept_rate": 1.0,
            "diagnostics": {
                "action_counts": {
                    "baseline": {"recruit": 20, "farm": 10},
                    "experiment": {"recruit": 8, "farm": 10},  # 8 < 20 / 2 -> triggers hint
                },
                "incidents": {
                    "experiment": {"deflections": 0},
                },
                "rejection_reasons": [],
            },
        }
        hint = generate_possible_cause_hint(summary)
        self.assertIn("LLM 徵兵偏少", hint)
        self.assertNotIn("有武將出奔", hint)
        self.assertNotIn("指令被拒比例偏高", hint)

    # 10. possible cause hint: defection trigger
    def test_possible_cause_hint_rule_defection(self):
        summary = {
            "orders_accept_rate": 1.0,
            "diagnostics": {
                "action_counts": {
                    "baseline": {"recruit": 10},
                    "experiment": {"recruit": 10},
                },
                "incidents": {
                    "experiment": {"deflections": 2},  # >= 1 -> triggers hint
                },
                "rejection_reasons": [],
            },
        }
        hint = generate_possible_cause_hint(summary)
        self.assertIn("有武將出奔，檢查冷落機制", hint)
        self.assertNotIn("LLM 徵兵偏少", hint)

    # 11. possible cause hint: high rejection rate trigger
    def test_possible_cause_hint_rule_high_rejection(self):
        summary = {
            "orders_accept_rate": 0.85,  # 1.0 - 0.85 = 15% > 10% -> triggers hint
            "diagnostics": {
                "action_counts": {
                    "baseline": {"recruit": 10},
                    "experiment": {"recruit": 10},
                },
                "incidents": {
                    "experiment": {"deflections": 0},
                },
                "rejection_reasons": [
                    {"reason": "insufficient gold: need N, have N", "count": 5}
                ],
            },
        }
        hint = generate_possible_cause_hint(summary)
        self.assertIn("指令被拒比例偏高，主因：insufficient gold: need N, have N", hint)

    # 12. possible cause hint: all normal
    def test_possible_cause_hint_rule_all_normal(self):
        summary = {
            "orders_accept_rate": 0.95,
            "diagnostics": {
                "action_counts": {
                    "baseline": {"recruit": 10},
                    "experiment": {"recruit": 10},
                },
                "incidents": {
                    "experiment": {"deflections": 0},
                },
                "rejection_reasons": [],
            },
        }
        hint = generate_possible_cause_hint(summary)
        self.assertIn("表現正常，未見明顯異常", hint)

    # 13. ConfigError: Chinese character in API key raises ConfigError, sends no request, no key in message
    def test_config_error_chinese_characters(self):
        env_var = "TEST_CHINESE_API_KEY"
        os.environ[env_var] = "sk-測試金鑰-xyz"
        try:
            completer = OpenAIChatCompleter(
                base_url="http://127.0.0.1:9999",
                model="test-model",
                api_key_env=env_var,
            )
            with patch("urllib.request.urlopen") as mock_url:
                with self.assertRaises(ConfigError) as cm:
                    completer("system prompt", "user prompt")
                mock_url.assert_not_called()

            err_msg = str(cm.exception)
            self.assertIn(env_var, err_msg)
            self.assertIn("含非 ASCII 或空白字元", err_msg)
            # Secret key content must NOT be leaked
            self.assertNotIn("sk-測試金鑰-xyz", err_msg)
            self.assertNotIn("測試金鑰", err_msg)
        finally:
            os.environ.pop(env_var, None)

    # 14. ConfigError: newline in API key raises ConfigError, sends no request
    def test_config_error_newline_in_key(self):
        env_var = "TEST_NEWLINE_API_KEY"
        os.environ[env_var] = "sk-validprefix\n"
        try:
            completer = OpenAIChatCompleter(
                base_url="http://127.0.0.1:9999",
                model="test-model",
                api_key_env=env_var,
            )
            with patch("urllib.request.urlopen") as mock_url:
                with self.assertRaises(ConfigError) as cm:
                    completer("system prompt", "user prompt")
                mock_url.assert_not_called()

            err_msg = str(cm.exception)
            self.assertIn(env_var, err_msg)
            self.assertNotIn("sk-validprefix", err_msg)
        finally:
            os.environ.pop(env_var, None)

    # 15. ConfigError: whitespace in API key raises ConfigError, sends no request
    def test_config_error_whitespace_in_key(self):
        env_var = "TEST_SPACE_API_KEY"
        os.environ[env_var] = "sk-key with space"
        try:
            completer = OpenAIChatCompleter(
                base_url="http://127.0.0.1:9999",
                model="test-model",
                api_key_env=env_var,
            )
            with patch("urllib.request.urlopen") as mock_url:
                with self.assertRaises(ConfigError) as cm:
                    completer("system prompt", "user prompt")
                mock_url.assert_not_called()

            err_msg = str(cm.exception)
            self.assertIn(env_var, err_msg)
            self.assertNotIn("sk-key with space", err_msg)
        finally:
            os.environ.pop(env_var, None)

    # 16. Circuit breaker trips immediately on ConfigError without waiting for 3 errors; real_calls == 0
    def test_circuit_breaker_trips_immediately_on_config_error(self):
        calls = 0

        def failing_inner(s: str, u: str) -> str:
            nonlocal calls
            calls += 1
            raise ConfigError("環境變數 TEST_KEY 的值含非 ASCII 或空白字元（可能貼成了佔位文字或多了換行）")

        cb = CircuitBreakerCompleter(failing_inner, max_consecutive_errors=3)
        self.assertFalse(cb.is_open)
        self.assertEqual(cb.real_calls, 0)

        # First call must trip the breaker immediately
        with self.assertRaises(ConfigError):
            cb("sys", "user")

        self.assertTrue(cb.is_open)
        self.assertEqual(cb.real_calls, 0, "real_calls must NOT increase on ConfigError")
        self.assertEqual(calls, 1)

        # Subsequent call must be short-circuited by BackendUnavailable
        with self.assertRaises(BackendUnavailable):
            cb("sys", "user")

        self.assertEqual(cb.real_calls, 0)
        self.assertEqual(calls, 1)

    # 17. LLMFactionAgent does not retry on ConfigError; raises directly
    def test_llm_agent_does_not_retry_on_config_error(self):
        calls = 0

        def failing_inner(s: str, u: str) -> str:
            nonlocal calls
            calls += 1
            raise ConfigError("環境變數 API_KEY 的值含非 ASCII 或空白字元（可能貼成了佔位文字或多了換行）")

        agent = LLMFactionAgent(failing_inner, max_retries=2)
        state = build_initial_state()
        cast = select_cast(state, "faction_1")
        view = build_faction_view(state, "faction_1", cast)

        with self.assertRaises(ConfigError):
            agent.decide(view)

        # Must not retry: call count must be 1 even with max_retries=2
        self.assertEqual(calls, 1)
        self.assertEqual(agent.usage["calls"], 0)

    # 18. render_markdown text when aborted or stopped early
    def test_render_markdown_aborted_and_stopped_early_texts(self):
        # Case A: aborted
        aborted_result = {
            "summary": {
                "seat": "faction_2",
                "seeds": [],
                "planned_seeds": [0, 1, 2],
                "baseline_win_rate": 0.0,
                "experiment_win_rate": 0.0,
                "win_rate_delta": 0.0,
                "mean_cities_delta": 0.0,
                "mean_troops_delta": 0.0,
                "orders_accept_rate": 1.0,
                "plan_failure_rate": 1.0,
                "delegated_per_turn": 0.0,
                "calls": 0,
                "est_tokens": 0,
                "parse_failures": 0,
                "errors": 1,
                "diagnostics": {},
            },
            "budget": {
                "max_calls": 20,
                "calls_used": 0,
                "stopped_early": False,
            },
            "per_seed": [],
            "aborted": True,
            "abort_reason": "後端連續失敗（1 次）：金鑰格式錯誤",
            "error_samples": ["金鑰格式錯誤"],
        }
        md_aborted = render_markdown(aborted_result)
        self.assertNotIn("未觸發提前終止", md_aborted)
        self.assertIn("已中止（後端連續失敗（1 次）：金鑰格式錯誤）", md_aborted)
        self.assertIn("計畫種子 3 個，實際完成 0 個", md_aborted)

        # Case B: stopped_early
        stopped_result = {
            "summary": {
                "seat": "faction_2",
                "seeds": [0],
                "planned_seeds": [0, 1],
                "baseline_win_rate": 0.0,
                "experiment_win_rate": 0.0,
                "win_rate_delta": 0.0,
                "mean_cities_delta": 0.0,
                "mean_troops_delta": 0.0,
                "orders_accept_rate": 1.0,
                "plan_failure_rate": 0.0,
                "delegated_per_turn": 0.0,
                "calls": 20,
                "est_tokens": 100,
                "parse_failures": 0,
                "errors": 0,
                "diagnostics": {},
            },
            "budget": {
                "max_calls": 20,
                "calls_used": 20,
                "stopped_early": True,
            },
            "per_seed": [],
            "aborted": False,
            "abort_reason": None,
            "error_samples": [],
        }
        md_stopped = render_markdown(stopped_result)
        self.assertNotIn("未觸發提前終止", md_stopped)
        self.assertIn("已中止（預算耗盡）", md_stopped)
        self.assertIn("計畫種子 2 個，實際完成 1 個", md_stopped)

    # 19. evaluate CLI subprocess: non-zero exit code when aborted
    def test_evaluate_cli_subprocess_aborted_nonzero_exit(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "slg.sim.evaluate",
                "--command",
                sys.executable,
                "-c",
                "import sys; sys.exit(1)",
                "--seeds",
                "0-2",
                "--turns",
                "2",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("⚠️ 後端連續失敗，評測已中止：", combined)
        self.assertIn("已中止（", combined)
        self.assertNotIn("未觸發提前終止", combined)


if __name__ == "__main__":
    unittest.main()
