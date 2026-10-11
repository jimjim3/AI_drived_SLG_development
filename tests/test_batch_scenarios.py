"""Tests for Task L: extra_body in OpenAIChatCompleter, scenarios (advantage), and batch_eval."""

from __future__ import annotations

import argparse
import dataclasses
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from slg.agents.backends import (
    CircuitBreakerCompleter,
    DemoCompleter,
    OpenAIChatCompleter,
    ScriptedCompleter,
)
from slg.agents.llm_agent import LLMFactionAgent
from slg.engine.initial_state import build_initial_state
from slg.schema import TurnLog
from slg.sim.batch_eval import batch_evaluate, render_summary_markdown
from slg.sim.evaluate import SharedCallCounter, evaluate
from slg.sim.headless import run_headless
from slg.sim.replay import replay
from slg.sim.run_llm import _parse_extra_body_json, build_completer


class MockOpenAIServerHandler(http.server.BaseHTTPRequestHandler):
    requests_received: list[dict] = []
    response_code = 200
    response_body = b'{"choices":[{"message":{"content":"mocked answer"}}]}'

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        self.__class__.requests_received.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": parsed,
        })
        self.send_response(self.__class__.response_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.__class__.response_body)

    def log_message(self, format, *args):
        pass


class TestBatchScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockOpenAIServerHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockOpenAIServerHandler.requests_received = []
        MockOpenAIServerHandler.response_code = 200
        MockOpenAIServerHandler.response_body = b'{"choices":[{"message":{"content":"mocked answer"}}]}'

    # 1. extra_body merged in request payload
    def test_openai_completer_extra_body_merged_in_request_payload(self):
        extra = {
            "chat_template_kwargs": {"enable_thinking": False},
            "custom_top_level": 42,
        }
        completer = OpenAIChatCompleter(
            base_url=f"http://127.0.0.1:{self.port}",
            model="qwen-local",
            extra_body=extra,
        )
        res = completer("system prompt", "user query")
        self.assertEqual(res, "mocked answer")
        self.assertEqual(len(MockOpenAIServerHandler.requests_received), 1)
        req = MockOpenAIServerHandler.requests_received[0]
        self.assertEqual(req["body"].get("chat_template_kwargs"), {"enable_thinking": False})
        self.assertEqual(req["body"].get("custom_top_level"), 42)
        self.assertEqual(req["body"].get("model"), "qwen-local")

    # 2. extra_body never overwrites model or messages
    def test_openai_completer_extra_body_never_overwrites_model_or_messages(self):
        extra = {
            "model": "evil-injected-model",
            "messages": [{"role": "user", "content": "evil-messages"}],
            "chat_template_kwargs": {"enable_thinking": False},
        }
        completer = OpenAIChatCompleter(
            base_url=f"http://127.0.0.1:{self.port}",
            model="original-model",
            extra_body=extra,
        )
        completer("real-sys", "real-user")
        self.assertEqual(len(MockOpenAIServerHandler.requests_received), 1)
        req = MockOpenAIServerHandler.requests_received[0]
        self.assertEqual(req["body"]["model"], "original-model")
        self.assertEqual(
            req["body"]["messages"],
            [
                {"role": "system", "content": "real-sys"},
                {"role": "user", "content": "real-user"},
            ],
        )
        self.assertEqual(req["body"].get("chat_template_kwargs"), {"enable_thinking": False})

    # 3. build_completer parses extra_body from json string and dict
    def test_build_completer_extra_body_from_json_string_and_dict(self):
        args_str = argparse.Namespace(
            demo=False,
            command=None,
            openai_base_url="http://127.0.0.1:8090",
            model="qwen",
            api_key_env=None,
            extra_body_json='{"chat_template_kwargs": {"enable_thinking": false}}',
            max_consecutive_errors=3,
        )
        cb1 = build_completer(args_str)
        self.assertIsInstance(cb1, CircuitBreakerCompleter)
        self.assertIsInstance(cb1.inner, OpenAIChatCompleter)
        self.assertEqual(cb1.inner.extra_body, {"chat_template_kwargs": {"enable_thinking": False}})

        args_dict = argparse.Namespace(
            demo=False,
            command=None,
            openai_base_url="http://127.0.0.1:8090",
            model="qwen",
            api_key_env=None,
            extra_body_json={"chat_template_kwargs": {"enable_thinking": False}},
            max_consecutive_errors=3,
        )
        cb2 = build_completer(args_dict)
        self.assertEqual(cb2.inner.extra_body, {"chat_template_kwargs": {"enable_thinking": False}})

    # 4. build_completer invalid extra_body_json raises ValueError
    def test_build_completer_invalid_extra_body_json_raises_value_error(self):
        args_bad = argparse.Namespace(
            demo=False,
            command=None,
            openai_base_url="http://127.0.0.1:8090",
            model="qwen",
            api_key_env=None,
            extra_body_json='{invalid json',
            max_consecutive_errors=3,
        )
        with self.assertRaises(ValueError):
            build_completer(args_bad)

        args_list = argparse.Namespace(
            demo=False,
            command=None,
            openai_base_url="http://127.0.0.1:8090",
            model="qwen",
            api_key_env=None,
            extra_body_json='[1, 2, 3]',
            max_consecutive_errors=3,
        )
        with self.assertRaises(ValueError):
            build_completer(args_list)

    # 5. CLI invalid extra_body_json produces argparse error and non-zero exit
    def test_cli_invalid_extra_body_json_produces_argparse_error(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        # Test evaluate CLI
        proc_eval = subprocess.run(
            [
                sys.executable,
                "-m",
                "slg.sim.evaluate",
                "--demo",
                "--extra-body-json",
                "{malformed json",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc_eval.returncode, 0)
        self.assertIn("error: argument --extra-body-json", proc_eval.stderr)

        # Test batch_eval CLI
        proc_batch = subprocess.run(
            [
                sys.executable,
                "-m",
                "slg.sim.batch_eval",
                "--demo",
                "--extra-body-json",
                "{malformed json",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc_batch.returncode, 0)
        self.assertIn("error: argument --extra-body-json", proc_batch.stderr)

    # 6. CLI non-dict extra_body_json produces argparse error and non-zero exit
    def test_cli_non_dict_extra_body_json_produces_argparse_error(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "slg.sim.evaluate",
                "--demo",
                "--extra-body-json",
                "[1, 2, 3]",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("error: argument --extra-body-json", proc.stderr)

    # 7. advantage scenario exact values and multipliers
    def test_advantage_scenario_exact_values_and_multipliers(self):
        st_def = build_initial_state("default")
        st_adv = build_initial_state("advantage")

        # faction_2 cities: troops x 2.5, gold x 1.5, defense unchanged
        for cid in ("luoyang", "wancheng", "hanzhong"):
            c_def = st_def.city(cid)
            c_adv = st_adv.city(cid)
            self.assertEqual(c_adv.owner, "faction_2")
            self.assertEqual(c_adv.troops, int(c_def.troops * 2.5))
            self.assertEqual(c_adv.gold, int(c_def.gold * 1.5))
            self.assertEqual(c_adv.defense, c_def.defense)
            self.assertEqual(c_adv.food, c_def.food)

        # Exact values check for faction_2
        self.assertEqual(st_adv.city("luoyang").troops, 2750)
        self.assertEqual(st_adv.city("luoyang").gold, 1350)
        self.assertEqual(st_adv.city("wancheng").troops, 1750)
        self.assertEqual(st_adv.city("wancheng").gold, 900)
        self.assertEqual(st_adv.city("hanzhong").troops, 1750)
        self.assertEqual(st_adv.city("hanzhong").gold, 900)

        # Adjacent enemy cities: xuchang, xiangyang troops x 0.5, defense unchanged
        for cid in ("xuchang", "xiangyang"):
            c_def = st_def.city(cid)
            c_adv = st_adv.city(cid)
            self.assertEqual(c_adv.troops, int(c_def.troops * 0.5))
            self.assertEqual(c_adv.defense, c_def.defense)
            self.assertEqual(c_adv.gold, c_def.gold)
            self.assertEqual(c_adv.food, c_def.food)

        self.assertEqual(st_adv.city("xuchang").troops, 700)
        self.assertEqual(st_adv.city("xiangyang").troops, 600)

        # Non-adjacent enemy cities: chenliu, jianye, wujun, kuaiji completely unchanged
        for cid in ("chenliu", "jianye", "wujun", "kuaiji"):
            c_def = st_def.city(cid)
            c_adv = st_adv.city(cid)
            self.assertEqual(c_adv.troops, c_def.troops)
            self.assertEqual(c_adv.gold, c_def.gold)
            self.assertEqual(c_adv.defense, c_def.defense)
            self.assertEqual(c_adv.food, c_def.food)

        # Officers, factions, adjacency unchanged
        self.assertEqual(dataclasses.asdict(st_adv)["officers"], dataclasses.asdict(st_def)["officers"])
        self.assertEqual(dataclasses.asdict(st_adv)["factions"], dataclasses.asdict(st_def)["factions"])
        self.assertEqual(st_adv.adjacency, st_def.adjacency)

    # 8. unknown scenario raises ValueError
    def test_unknown_scenario_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_initial_state("bogus_scenario")
        with self.assertRaises(ValueError):
            run_headless(scenario="invalid_one")

    # 9. default scenario bitwise identical to baseline build_initial_state()
    def test_default_scenario_bitwise_identical_to_baseline(self):
        st_def = build_initial_state("default")
        st_none = build_initial_state()
        self.assertEqual(st_def, st_none)
        self.assertEqual(dataclasses.asdict(st_def), dataclasses.asdict(st_none))

    # 10. TurnLog.scenario and replay consistency for advantage scenario
    def test_turnlog_scenario_field_and_replay_consistency_advantage(self):
        res = run_headless(seed=7, turns=15, scenario="advantage")
        self.assertEqual(res.log.scenario, "advantage")

        rep = replay(res.log)
        self.assertEqual(rep.final_state, res.final_state)
        self.assertEqual(rep.events, res.events)
        self.assertEqual(rep.winner, res.winner)

    # 11. TurnLog.scenario and replay consistency for default scenario
    def test_turnlog_scenario_default_replay_consistency(self):
        res = run_headless(seed=7, turns=15, scenario="default")
        self.assertEqual(res.log.scenario, "default")

        rep = replay(res.log)
        self.assertEqual(rep.final_state, res.final_state)
        self.assertEqual(rep.events, res.events)
        self.assertEqual(rep.winner, res.winner)

    # 12. Rule-based agent runs to completion on 40 seeds under advantage scenario
    def test_rule_based_agent_advantage_scenario_40_seeds_valid_equals_decisions(self):
        for s in range(40):
            res = run_headless(seed=s, turns=20, scenario="advantage")
            self.assertGreater(res.stats["decisions"], 0)
            self.assertEqual(res.stats["valid"], res.stats["decisions"])
            self.assertEqual(res.stats["rejected"], 0)

    # 13. batch_eval file outputs and SUMMARY content
    def test_batch_eval_file_outputs_and_summary_content(self):
        seats = ["faction_1", "faction_2"]
        scenarios = ["default", "advantage"]
        seeds = [0, 1]
        with tempfile.TemporaryDirectory() as tmpdir:
            batch_res = batch_evaluate(
                seats=seats,
                scenarios=scenarios,
                seeds=seeds,
                turns=5,
                completer_builder=lambda: DemoCompleter(),
                outdir=tmpdir,
                workers=1,
            )

            # Check files exist
            expected_files = [
                "default__faction_1.md",
                "default__faction_1.json",
                "default__faction_2.md",
                "default__faction_2.json",
                "advantage__faction_1.md",
                "advantage__faction_1.json",
                "advantage__faction_2.md",
                "advantage__faction_2.json",
                "SUMMARY.md",
                "SUMMARY.json",
            ]
            for fname in expected_files:
                fpath = os.path.join(tmpdir, fname)
                self.assertTrue(os.path.exists(fpath), f"Missing expected output file: {fname}")

            # Check SUMMARY.json structure and contents
            with open(os.path.join(tmpdir, "SUMMARY.json"), "r", encoding="utf-8") as f:
                sum_json = json.load(f)

            self.assertEqual(len(sum_json["summary"]), 4)
            for row in sum_json["summary"]:
                self.assertIn("combination", row)
                self.assertIn("scenario", row)
                self.assertIn("seat", row)
                self.assertIn("win_rate_delta", row)
                self.assertIn("mean_troops_delta", row)
                self.assertIn("mean_cities_delta", row)
                self.assertIn("orders_accept_rate", row)
                self.assertIn("siege_attempts", row)
                self.assertIn("siege_captured", row)
                self.assertIn("calls", row)
                self.assertIn("est_tokens", row)
                self.assertIn("aborted", row)
                self.assertFalse(row["aborted"])

            # Check SUMMARY.md table content
            with open(os.path.join(tmpdir, "SUMMARY.md"), "r", encoding="utf-8") as f:
                md_text = f.read()

            self.assertIn("SLG 批次評測總結報告", md_text)
            self.assertIn("default__faction_1", md_text)
            self.assertIn("advantage__faction_2", md_text)
            self.assertIn("席位勝率差", md_text)
            self.assertIn("攻城 (嘗試/成功)", md_text)

    # 14. workers 2 produces identical output to workers 1 (determinism)
    def test_batch_eval_workers_determinism(self):
        seats = ["faction_1", "faction_2"]
        scenarios = ["default", "advantage"]
        seeds = [0, 1]

        with tempfile.TemporaryDirectory() as dir1, tempfile.TemporaryDirectory() as dir2:
            res1 = batch_evaluate(
                seats=seats,
                scenarios=scenarios,
                seeds=seeds,
                turns=5,
                completer_builder=lambda: DemoCompleter(),
                outdir=dir1,
                workers=1,
            )
            res2 = batch_evaluate(
                seats=seats,
                scenarios=scenarios,
                seeds=seeds,
                turns=5,
                completer_builder=lambda: DemoCompleter(),
                outdir=dir2,
                workers=2,
            )

            # Compare in-memory results (summary and combinations)
            self.assertEqual(res1["summary"], res2["summary"])
            self.assertEqual(res1["combinations"], res2["combinations"])

            # Compare generated SUMMARY.json files (summary and combinations)
            with open(os.path.join(dir1, "SUMMARY.json")) as f1, open(os.path.join(dir2, "SUMMARY.json")) as f2:
                data1 = json.load(f1)
                data2 = json.load(f2)
                self.assertEqual(data1["summary"], data2["summary"])
                self.assertEqual(data1["combinations"], data2["combinations"])

            # Compare all individual combo JSON and MD files
            for scen in scenarios:
                for seat in seats:
                    cname = f"{scen}__{seat}.json"
                    with open(os.path.join(dir1, cname)) as f1, open(os.path.join(dir2, cname)) as f2:
                        self.assertEqual(json.load(f1), json.load(f2))
                    mname = f"{scen}__{seat}.md"
                    with open(os.path.join(dir1, mname)) as f1, open(os.path.join(dir2, mname)) as f2:
                        self.assertEqual(f1.read(), f2.read())

    # 15. Single combination failure does not affect other combinations
    def test_batch_eval_single_combo_failure_isolation(self):
        seats = ["faction_1", "faction_2"]
        scenarios = ["default", "advantage"]
        seeds = [0]

        # Combo (advantage, faction_2) backend fails and trips circuit breaker
        def factory_builder(scen: str, seat: str):
            if scen == "advantage" and seat == "faction_2":
                bad_comp = ScriptedCompleter([RuntimeError("upstream crash")] * 10)
                return lambda budget: LLMFactionAgent(budget.wrap(bad_comp))
            return lambda budget: LLMFactionAgent(budget.wrap(DemoCompleter()))

        with tempfile.TemporaryDirectory() as tmpdir:
            res = batch_evaluate(
                seats=seats,
                scenarios=scenarios,
                seeds=seeds,
                turns=3,
                agent_factory_builder=factory_builder,
                outdir=tmpdir,
                workers=1,
            )

            combos = res["combinations"]
            self.assertTrue(combos["advantage__faction_2"]["aborted"])
            self.assertFalse(combos["default__faction_1"]["aborted"])
            self.assertFalse(combos["default__faction_2"]["aborted"])
            self.assertFalse(combos["advantage__faction_1"]["aborted"])

            # Verify files exist for all
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "advantage__faction_2.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "default__faction_1.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "SUMMARY.md")))

    # 16. Each combination gets an independent circuit breaker
    def test_batch_eval_independent_circuit_breakers(self):
        args = argparse.Namespace(
            demo=False,
            command=None,
            openai_base_url="http://127.0.0.1:8090",
            model="test",
            api_key_env=None,
            extra_body_json=None,
            max_consecutive_errors=2,
        )
        cb1 = build_completer(args)
        cb2 = build_completer(args)

        self.assertIsNot(cb1, cb2)
        cb1.is_open = True
        self.assertTrue(cb1.is_open)
        self.assertFalse(cb2.is_open)

    # 17. Total call budget protection across all combinations
    def test_batch_eval_total_call_budget_protection(self):
        seats = ["faction_1", "faction_2"]
        scenarios = ["default", "advantage"]
        seeds = [0, 1]

        # Limit total calls to 5
        res = batch_evaluate(
            seats=seats,
            scenarios=scenarios,
            seeds=seeds,
            turns=5,
            completer_builder=lambda: DemoCompleter(),
            max_calls=5,
            workers=1,
        )

        total_used = res["total_budget"]["calls_used"]
        self.assertLessEqual(total_used, 5)
        self.assertTrue(res["total_budget"]["stopped_early"])

        sum_calls = sum(r["calls"] for r in res["summary"])
        self.assertEqual(sum_calls, total_used)

    # 18. Environment secret key never leaks into batch files or reports
    def test_batch_eval_no_api_key_leak(self):
        secret = "sk-secret-batch-token-do-not-leak-999"
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        env["MY_BATCH_SECRET_KEY"] = secret

        with tempfile.TemporaryDirectory() as tmpdir:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "slg.sim.batch_eval",
                    "--demo",
                    "--seats",
                    "faction_1,faction_2",
                    "--scenarios",
                    "default",
                    "--seeds",
                    "0",
                    "--turns",
                    "2",
                    "--api-key-env",
                    "MY_BATCH_SECRET_KEY",
                    "--outdir",
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn(secret, proc.stdout)
            self.assertNotIn(secret, proc.stderr)

            # Check SUMMARY.md and SUMMARY.json
            with open(os.path.join(tmpdir, "SUMMARY.md")) as f:
                self.assertNotIn(secret, f.read())
            with open(os.path.join(tmpdir, "SUMMARY.json")) as f:
                self.assertNotIn(secret, f.read())

            # Check individual files
            with open(os.path.join(tmpdir, "default__faction_1.md")) as f:
                self.assertNotIn(secret, f.read())
            with open(os.path.join(tmpdir, "default__faction_1.json")) as f:
                self.assertNotIn(secret, f.read())

    # 19. evaluate CLI with scenario and extra_body_json flags
    def test_evaluate_cli_scenario_and_extra_body_flags(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "eval_rep.md")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "slg.sim.evaluate",
                    "--demo",
                    "--scenario",
                    "advantage",
                    "--extra-body-json",
                    '{"chat_template_kwargs": {"enable_thinking": false}}',
                    "--seeds",
                    "0",
                    "--turns",
                    "3",
                    "--out",
                    out_file,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
            with open(out_file) as f:
                content = f.read()
            self.assertIn("advantage", content)
            self.assertIn("情境 (Scenario)", content)

    # 20. run_llm CLI with scenario flag saves scenario in TurnLog
    def test_run_llm_cli_scenario_flag(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "turnlog.json")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "slg.sim.run_llm",
                    "--demo",
                    "--scenario",
                    "advantage",
                    "--turns",
                    "2",
                    "--save-log",
                    log_file,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
            with open(log_file) as f:
                log_data = json.load(f)
            self.assertEqual(log_data.get("scenario"), "advantage")


if __name__ == "__main__":
    unittest.main()
