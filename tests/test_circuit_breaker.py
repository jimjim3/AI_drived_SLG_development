"""Tests for circuit breaker protection and diagnostic error sampling."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

from slg.agents.backends import (
    BackendUnavailable,
    CircuitBreakerCompleter,
    ScriptedCompleter,
)
from slg.agents.base import AgentError
from slg.agents.llm_agent import LLMFactionAgent
from slg.engine.initial_state import build_initial_state
from slg.engine.view import build_faction_view, select_cast
from slg.sim.evaluate import evaluate, render_markdown


class CountingMockCompleter:
    """Mock completer that tracks call count and can fail or succeed."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.call_count = 0
        self.failure = failure

    def __call__(self, system: str, user: str) -> str:
        self.call_count += 1
        if self.failure is not None:
            raise self.failure
        return '{"orders":[],"chronicle":"測試","next_cast":[]}'


class TestCircuitBreaker(unittest.TestCase):
    # 1. 斷路器計數與歸零
    def test_circuit_breaker_consecutive_errors_counting_and_reset(self):
        calls = []

        def mock(s: str, u: str) -> str:
            calls.append(len(calls))
            if len(calls) in (1, 2):
                raise RuntimeError(f"error {len(calls)}")
            return "ok"

        cb = CircuitBreakerCompleter(mock, max_consecutive_errors=3)

        with self.assertRaises(RuntimeError):
            cb("sys", "u")
        self.assertEqual(cb.consecutive_errors, 1)
        self.assertFalse(cb.is_open)

        with self.assertRaises(RuntimeError):
            cb("sys", "u")
        self.assertEqual(cb.consecutive_errors, 2)
        self.assertFalse(cb.is_open)

        res = cb("sys", "u")
        self.assertEqual(res, "ok")
        self.assertEqual(cb.consecutive_errors, 0)
        self.assertFalse(cb.is_open)

    # 2. 達到上限跳脫
    def test_circuit_breaker_trips_at_max_consecutive_errors(self):
        failing = CountingMockCompleter(failure=RuntimeError("persistent crash"))
        cb = CircuitBreakerCompleter(failing, max_consecutive_errors=3)

        for i in range(1, 4):
            with self.assertRaises(RuntimeError) as cm:
                cb("sys", f"u{i}")
            self.assertIn("persistent crash", str(cm.exception))
            self.assertEqual(cb.consecutive_errors, i)

        self.assertTrue(cb.is_open)
        self.assertEqual(failing.call_count, 3)

    # 3. open 後不呼叫 inner，直接拋 BackendUnavailable
    def test_circuit_breaker_open_blocks_inner_call(self):
        failing = CountingMockCompleter(failure=RuntimeError("api error"))
        cb = CircuitBreakerCompleter(failing, max_consecutive_errors=2)

        with self.assertRaises(RuntimeError):
            cb("sys", "u1")
        with self.assertRaises(RuntimeError):
            cb("sys", "u2")
        self.assertTrue(cb.is_open)
        self.assertEqual(failing.call_count, 2)

        # Subsequent calls must NOT reach failing mock
        for _ in range(4):
            with self.assertRaises(BackendUnavailable):
                cb("sys", "u_subsequent")

        self.assertEqual(failing.call_count, 2, "Inner completer must not be called when circuit breaker is open")

    # 4. real_calls 與短路次數
    def test_circuit_breaker_real_calls_and_short_circuits(self):
        failing = CountingMockCompleter(failure=RuntimeError("service unavailable"))
        cb = CircuitBreakerCompleter(failing, max_consecutive_errors=3)

        # 3 initial calls trip the breaker
        for _ in range(3):
            with self.assertRaises(RuntimeError):
                cb("sys", "u")

        self.assertEqual(cb.real_calls, 3)

        # 4 more calls are short-circuited
        short_circuit_count = 0
        for _ in range(4):
            try:
                cb("sys", "u")
            except BackendUnavailable:
                short_circuit_count += 1

        self.assertEqual(short_circuit_count, 4)
        self.assertEqual(cb.real_calls, 3)
        self.assertEqual(failing.call_count, 3)

    # 5. max_consecutive_errors <= 0 停用斷路器
    def test_circuit_breaker_disabled_when_max_consecutive_errors_le_zero(self):
        for disabled_val in (0, -1, -5):
            failing = CountingMockCompleter(failure=RuntimeError("ignore limit"))
            cb = CircuitBreakerCompleter(failing, max_consecutive_errors=disabled_val)

            for _ in range(8):
                with self.assertRaises(RuntimeError):
                    cb("sys", "u")

            self.assertFalse(cb.is_open)
            self.assertEqual(cb.real_calls, 8)
            self.assertEqual(failing.call_count, 8)

    # 6. BackendUnavailable 訊息含最後錯誤與連續失敗次數
    def test_backend_unavailable_message_contains_last_error_and_count(self):
        specific_error = "Connection reset by peer (errno 104)"
        failing = CountingMockCompleter(failure=ConnectionResetError(specific_error))
        cb = CircuitBreakerCompleter(failing, max_consecutive_errors=3)

        for _ in range(3):
            with self.assertRaises(ConnectionResetError):
                cb("sys", "u")

        self.assertTrue(cb.is_open)
        with self.assertRaises(BackendUnavailable) as cm:
            cb("sys", "u")

        exc = cm.exception
        self.assertIsInstance(exc, RuntimeError)
        msg = str(exc)
        self.assertIn(specific_error, msg)
        self.assertIn("3", msg)

    # 7. 間歇性失敗不觸發斷路器
    def test_intermittent_failures_do_not_trip_circuit_breaker(self):
        step = 0

        def alternating(s: str, u: str) -> str:
            nonlocal step
            step += 1
            if step % 2 == 1:
                raise RuntimeError(f"odd failure {step}")
            return '{"orders":[],"chronicle":"OK","next_cast":[]}'

        cb = CircuitBreakerCompleter(alternating, max_consecutive_errors=2)

        for _ in range(10):
            with self.assertRaises(RuntimeError):
                cb("sys", "u")
            self.assertEqual(cb.consecutive_errors, 1)
            self.assertFalse(cb.is_open)

            res = cb("sys", "u")
            self.assertIn("OK", res)
            self.assertEqual(cb.consecutive_errors, 0)
            self.assertFalse(cb.is_open)

        self.assertFalse(cb.is_open)
        self.assertEqual(cb.real_calls, 20)

    # 8. errors_seen 去重
    def test_errors_seen_deduplication(self):
        err = RuntimeError("repeated backend error")
        agent = LLMFactionAgent(CountingMockCompleter(failure=err), max_retries=2)
        state = build_initial_state()
        cast = select_cast(state, "faction_1")
        view = build_faction_view(state, "faction_1", cast)

        with self.assertRaises(AgentError):
            agent.decide(view)

        self.assertEqual(len(agent.errors_seen), 1)
        self.assertEqual(agent.errors_seen[0], "repeated backend error")

    # 9. errors_seen 截斷 300 字
    def test_errors_seen_truncation(self):
        long_message = "X" * 600
        err = RuntimeError(long_message)
        agent = LLMFactionAgent(CountingMockCompleter(failure=err), max_retries=0)
        state = build_initial_state()
        cast = select_cast(state, "faction_1")
        view = build_faction_view(state, "faction_1", cast)

        with self.assertRaises(AgentError):
            agent.decide(view)

        self.assertEqual(len(agent.errors_seen), 1)
        self.assertEqual(len(agent.errors_seen[0]), 300)
        self.assertEqual(agent.errors_seen[0], "X" * 300)

    # 10. errors_seen 上限 5 筆
    def test_errors_seen_max_five_entries(self):
        idx = 0

        def distinct_errors(s: str, u: str) -> str:
            nonlocal idx
            idx += 1
            raise RuntimeError(f"error code #{idx}")

        agent = LLMFactionAgent(distinct_errors, max_retries=0)
        state = build_initial_state()
        cast = select_cast(state, "faction_1")
        view = build_faction_view(state, "faction_1", cast)

        for _ in range(10):
            with self.assertRaises(AgentError):
                agent.decide(view)

        self.assertEqual(len(agent.errors_seen), 5)
        self.assertEqual(agent.errors_seen, [f"error code #{i}" for i in range(1, 6)])

    # 11. 解析失敗前綴 "parse: "
    def test_errors_seen_parse_failure_prefix(self):
        completer = ScriptedCompleter(["not valid json at all"])
        agent = LLMFactionAgent(completer, max_retries=0)
        state = build_initial_state()
        cast = select_cast(state, "faction_1")
        view = build_faction_view(state, "faction_1", cast)

        with self.assertRaises(AgentError):
            agent.decide(view)

        self.assertEqual(len(agent.errors_seen), 1)
        self.assertTrue(agent.errors_seen[0].startswith("parse: "))

    # 12. evaluate 永遠失敗 + max_calls=40 -> aborted=True, calls_used=3 (不是 40), error_samples 非空
    def test_evaluate_failing_completer_aborted_and_calls_used_three(self):
        failing = CountingMockCompleter(failure=RuntimeError("quota exceeded 429"))
        res = evaluate(
            seeds=[0],
            turns=5,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(failing)),
            max_calls=40,
            max_consecutive_errors=3,
        )

        self.assertTrue(res["aborted"])
        self.assertEqual(res["budget"]["calls_used"], 3)
        self.assertEqual(res["summary"]["calls"], 3)
        self.assertEqual(failing.call_count, 3)
        self.assertGreater(len(res["error_samples"]), 0)
        self.assertIn("quota exceeded 429", res["abort_reason"])

    # 13. evaluate stopped 後不再開始新種子（3 個種子只有第 1 個跑完）
    def test_evaluate_stopped_does_not_start_new_seeds(self):
        failing = CountingMockCompleter(failure=RuntimeError("backend dead"))
        res = evaluate(
            seeds=[0, 1, 2],
            turns=4,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(failing)),
            max_calls=40,
            max_consecutive_errors=3,
        )

        self.assertTrue(res["aborted"])
        self.assertEqual(len(res["per_seed"]), 1)
        self.assertEqual(res["per_seed"][0]["seed"], 0)
        self.assertEqual(res["budget"]["calls_used"], 3)
        self.assertEqual(failing.call_count, 3)

    # 14. 報告含警告與錯誤樣本且不含假金鑰
    def test_evaluate_report_warning_and_error_samples_fake_key_redacted(self):
        fake_key = "sk-test-123456"
        env_var = "TEST_EVAL_SECRET_KEY"
        os.environ[env_var] = fake_key
        try:
            failing = CountingMockCompleter(
                failure=RuntimeError(f"Authentication failed with key: {fake_key}")
            )
            res = evaluate(
                seeds=[0],
                turns=3,
                seat="faction_2",
                agent_factory=lambda b: LLMFactionAgent(b.wrap(failing)),
                max_calls=20,
                max_consecutive_errors=3,
                api_key_env=env_var,
            )

            md = render_markdown(res)

            # Warning at the top
            self.assertIn("⚠️ 後端連續失敗，評測已中止：", md)
            # Error samples section
            self.assertIn("## 錯誤樣本", md)
            # Fake key must be redacted everywhere
            self.assertNotIn(fake_key, md)
            self.assertIn("[REDACTED]", md)

            # In result dict
            for err in res["error_samples"]:
                self.assertNotIn(fake_key, err)
                self.assertIn("[REDACTED]", err)
            self.assertNotIn(fake_key, res["abort_reason"])
            self.assertIn("[REDACTED]", res["abort_reason"])
        finally:
            os.environ.pop(env_var, None)

    # 15. 若全部 LLM 呼叫皆失敗，摘要旁註明「實驗組實為規則 AI 代打，結果無效」
    def test_evaluate_all_llm_failed_disclaimer_in_report(self):
        failing = CountingMockCompleter(failure=RuntimeError("all fail"))
        res = evaluate(
            seeds=[0],
            turns=3,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(failing)),
            max_calls=20,
            max_consecutive_errors=3,
        )
        md = render_markdown(res)
        self.assertIn("實驗組實為規則 AI 代打，結果無效", md)

    # 16. run_llm CLI subprocess: 失敗 command 結束碼非 0 且輸出含警告
    def test_run_llm_cli_subprocess_failing_command_nonzero_and_warning(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "slg.sim.run_llm",
                "--command",
                sys.executable,
                "-c",
                "import sys; sys.exit(1)",
                "--turns",
                "3",
                "--seed",
                "42",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        combined_output = proc.stdout + proc.stderr
        self.assertIn("⚠️ 斷路器已跳脫", combined_output)

    # 17. evaluate CLI subprocess: 失敗 command 結束碼非 0 且輸出含中止警告
    def test_evaluate_cli_subprocess_failing_command_nonzero_and_warning(self):
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
                "3",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        combined_output = proc.stdout + proc.stderr
        self.assertIn("⚠️ 後端連續失敗，評測已中止：", combined_output)


if __name__ == "__main__":
    unittest.main()
