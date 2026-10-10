"""Unit tests for slg.sim.evaluate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest

from slg.agents.backends import CommandCompleter, DemoCompleter, OpenAIChatCompleter
from slg.agents.base import FactionAgent
from slg.agents.llm_agent import LLMFactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.view import FactionView
from slg.schema import AgentDecision, FactionPlan
from slg.sim.evaluate import (
    CallBudget,
    evaluate,
    parse_seeds,
    render_markdown,
)
from slg.sim.headless import run_headless
from slg.sim.run_llm import build_completer


class AlwaysRestAgent(FactionAgent):
    """FactionAgent that explicitly orders all cast officers to rest."""

    name = "always_rest"

    def decide(self, view: FactionView) -> FactionPlan:
        orders = []
        for officer in view.cast:
            orders.append(
                AgentDecision(
                    officer_id=officer["id"],
                    action="rest",
                    params={},
                    memo="休息",
                )
            )
        return FactionPlan(orders=tuple(orders), chronicle="全體休息")


class CrashingAgent(FactionAgent):
    """FactionAgent that always raises an error to trigger plan_failures."""

    name = "crashing"

    def decide(self, view: FactionView) -> FactionPlan:
        raise RuntimeError("simulated crash")


class TestEvaluate(unittest.TestCase):
    # 1-7: Seed parsing tests
    def test_parse_seeds_range(self):
        self.assertEqual(parse_seeds("0-3"), [0, 1, 2, 3])
        self.assertEqual(parse_seeds("4-4"), [4])

    def test_parse_seeds_comma_list(self):
        self.assertEqual(parse_seeds("1,3,5"), [1, 3, 5])
        self.assertEqual(parse_seeds(" 2 , 4 , 6 "), [2, 4, 6])

    def test_parse_seeds_mixed(self):
        self.assertEqual(parse_seeds("0-2,5,7-8"), [0, 1, 2, 5, 7, 8])

    def test_parse_seeds_single(self):
        self.assertEqual(parse_seeds("42"), [42])

    def test_parse_seeds_invalid_non_integer(self):
        with self.assertRaises(ValueError):
            parse_seeds("abc")
        with self.assertRaises(ValueError):
            parse_seeds("1-a")

    def test_parse_seeds_invalid_range_descending(self):
        with self.assertRaises(ValueError):
            parse_seeds("5-2")

    def test_parse_seeds_invalid_empty_or_malformed(self):
        with self.assertRaises(ValueError):
            parse_seeds("")
        with self.assertRaises(ValueError):
            parse_seeds("   ")
        with self.assertRaises(ValueError):
            parse_seeds("1,,3")
        with self.assertRaises(ValueError):
            parse_seeds("1-2-3")

    # 8: Structure and types with DemoCompleter over 3 seeds
    def test_evaluate_demo_completer_structure_and_types(self):
        seeds = [0, 1, 2]
        res = evaluate(
            seeds=seeds,
            turns=3,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
            max_calls=60,
        )

        self.assertEqual(set(res.keys()), {"per_seed", "summary", "budget"})
        self.assertEqual(len(res["per_seed"]), 3)

        # per_seed structure
        for item in res["per_seed"]:
            self.assertIn("seed", item)
            self.assertIn("baseline", item)
            self.assertIn("experiment", item)

            b = item["baseline"]
            self.assertTrue(b["winner"] is None or isinstance(b["winner"], str))
            self.assertIsInstance(b["cities"], int)
            self.assertIsInstance(b["troops"], int)

            e = item["experiment"]
            self.assertTrue(e["winner"] is None or isinstance(e["winner"], str))
            self.assertIsInstance(e["cities"], int)
            self.assertIsInstance(e["troops"], int)
            self.assertIsInstance(e["stats"], dict)
            self.assertIsInstance(e["usage"], dict)

        # summary structure and types
        s = res["summary"]
        self.assertEqual(s["seat"], "faction_2")
        self.assertEqual(s["seeds"], [0, 1, 2])
        self.assertIsInstance(s["baseline_win_rate"], float)
        self.assertIsInstance(s["experiment_win_rate"], float)
        self.assertIsInstance(s["win_rate_delta"], float)
        self.assertIsInstance(s["mean_cities_delta"], float)
        self.assertIsInstance(s["mean_troops_delta"], float)
        self.assertIsInstance(s["orders_accept_rate"], float)
        self.assertIsInstance(s["plan_failure_rate"], float)
        self.assertIsInstance(s["delegated_per_turn"], float)
        self.assertIsInstance(s["calls"], int)
        self.assertIsInstance(s["est_tokens"], int)
        self.assertIsInstance(s["parse_failures"], int)
        self.assertIsInstance(s["errors"], int)

        # budget structure
        bgt = res["budget"]
        self.assertEqual(bgt["max_calls"], 60)
        self.assertEqual(bgt["calls_used"], 9)  # 3 turns * 3 seeds = 9 calls
        self.assertFalse(bgt["stopped_early"])

        # JSON serializability
        dumped = json.dumps(res, ensure_ascii=False)
        self.assertIn('"per_seed"', dumped)
        self.assertIn('"summary"', dumped)

    # 9: Baseline matches direct run_headless
    def test_evaluate_baseline_matches_run_headless(self):
        seeds = [7, 13]
        res = evaluate(
            seeds=seeds,
            turns=4,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
        )

        for s_idx, seed in enumerate(seeds):
            direct = run_headless(seed=seed, turns=4)
            b = res["per_seed"][s_idx]["baseline"]

            self.assertEqual(b["winner"], direct.winner)
            direct_cities = len(direct.final_state.cities_of("faction_2"))
            direct_troops = sum(c.troops for c in direct.final_state.cities_of("faction_2"))
            self.assertEqual(b["cities"], direct_cities)
            self.assertEqual(b["troops"], direct_troops)

    # 10: Delta calculation matches hand calculation (discriminative with non-zero delta)
    def test_win_rate_delta_and_mean_deltas_hand_calculated(self):
        seeds = [0, 1, 2]
        res = evaluate(
            seeds=seeds,
            turns=5,
            seat="faction_2",
            agent_factory=lambda: AlwaysRestAgent(),
        )

        # Hand-calculate expected values
        b_wins = sum(1 for item in res["per_seed"] if item["baseline"]["winner"] == "faction_2")
        e_wins = sum(1 for item in res["per_seed"] if item["experiment"]["winner"] == "faction_2")
        exp_b_rate = b_wins / len(seeds)
        exp_e_rate = e_wins / len(seeds)
        exp_wr_delta = exp_e_rate - exp_b_rate

        exp_c_delta = sum(
            item["experiment"]["cities"] - item["baseline"]["cities"]
            for item in res["per_seed"]
        ) / len(seeds)
        exp_t_delta = sum(
            item["experiment"]["troops"] - item["baseline"]["troops"]
            for item in res["per_seed"]
        ) / len(seeds)

        # Assert exact equality
        self.assertAlmostEqual(res["summary"]["baseline_win_rate"], exp_b_rate)
        self.assertAlmostEqual(res["summary"]["experiment_win_rate"], exp_e_rate)
        self.assertAlmostEqual(res["summary"]["win_rate_delta"], exp_wr_delta)
        self.assertAlmostEqual(res["summary"]["mean_cities_delta"], exp_c_delta)
        self.assertAlmostEqual(res["summary"]["mean_troops_delta"], exp_t_delta)

        # Discriminative assertion: deltas must be non-zero because resting loses troops/cities
        self.assertNotEqual(exp_t_delta, 0.0)

    # 11: Orders accept rate is None when no orders exist
    def test_orders_accept_rate_none_when_no_orders(self):
        class NoOrderAgent(FactionAgent):
            name = "no_orders"
            def decide(self, view: FactionView) -> FactionPlan:
                return FactionPlan(orders=())

        res = evaluate(
            seeds=[0],
            turns=3,
            seat="faction_2",
            agent_factory=lambda: NoOrderAgent(),
        )
        self.assertIsNone(res["summary"]["orders_accept_rate"])

    # 12: Plan failure rate and delegated_per_turn
    def test_plan_failure_rate_and_delegated_per_turn(self):
        turns = 4
        seeds = [0, 1]
        res = evaluate(
            seeds=seeds,
            turns=turns,
            seat="faction_2",
            agent_factory=lambda: CrashingAgent(),
        )
        total_turns = turns * len(seeds)
        self.assertEqual(res["summary"]["plan_failure_rate"], 1.0)
        self.assertGreater(res["summary"]["delegated_per_turn"], 0.0)

    # 13: Budget protection: small max_calls stops early across seeds
    def test_budget_small_max_calls_stops_early(self):
        res = evaluate(
            seeds=[0, 1, 2],
            turns=5,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
            max_calls=3,
        )

        self.assertTrue(res["budget"]["stopped_early"])
        self.assertEqual(res["budget"]["calls_used"], 3)
        self.assertLessEqual(res["budget"]["calls_used"], 3)
        self.assertEqual(len(res["per_seed"]), 1)

    # 14: In-game budget exceeded exception handled safely
    def test_budget_in_game_completer_exception_safety_net(self):
        res = evaluate(
            seeds=[0],
            turns=6,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
            max_calls=2,
        )

        self.assertTrue(res["budget"]["stopped_early"])
        self.assertEqual(res["budget"]["calls_used"], 2)
        self.assertLessEqual(res["budget"]["calls_used"], 2)

        exp_stats = res["per_seed"][0]["experiment"]["stats"]
        self.assertEqual(exp_stats["valid"], exp_stats["decisions"])
        self.assertGreater(exp_stats["plan_failures"], 0)

    # 15: Budget unlimited runs all seeds
    def test_budget_unlimited_runs_all_seeds(self):
        res = evaluate(
            seeds=[0, 1],
            turns=3,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
            max_calls=None,
        )

        self.assertFalse(res["budget"]["stopped_early"])
        self.assertIsNone(res["budget"]["max_calls"])
        self.assertEqual(len(res["per_seed"]), 2)
        self.assertEqual(res["budget"]["calls_used"], 6)

    # 16: render_markdown contains key numbers and required disclaimer
    def test_render_markdown_contains_summary_numbers_and_disclaimer(self):
        res = evaluate(
            seeds=[0],
            turns=3,
            seat="faction_2",
            agent_factory=lambda b: LLMFactionAgent(b.wrap(DemoCompleter())),
        )
        md = render_markdown(res)

        self.assertIn("同座位比較、樣本數小時差異不具統計顯著性", md)
        self.assertIn("faction_2", md)
        self.assertIn("SLG 勢力決策評測報告", md)
        self.assertIn(f"{res['summary']['baseline_win_rate']:.1%}", md)
        self.assertIn(f"{res['summary']['experiment_win_rate']:.1%}", md)
        self.assertIn(str(res['summary']['calls']), md)

    # 17: CLI subprocess demo generates md and json
    def test_cli_subprocess_demo_generates_md_and_json(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "rep.md")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "slg.sim.evaluate",
                    "--demo",
                    "--seeds",
                    "0-2",
                    "--turns",
                    "5",
                    "--out",
                    out_path,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, f"stderr: {proc.stderr}")
            self.assertTrue(os.path.exists(out_path))

            # Both out_path.json and out_path[:-3] + .json should exist
            json_path = out_path + ".json"
            alt_json_path = os.path.join(tmpdir, "rep.json")
            self.assertTrue(os.path.exists(json_path) or os.path.exists(alt_json_path))

            active_json = json_path if os.path.exists(json_path) else alt_json_path
            with open(active_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("per_seed", data)
            self.assertIn("summary", data)
            self.assertIn("budget", data)
            self.assertEqual(len(data["per_seed"]), 3)

    # 18: CLI subprocess no backend fails
    def test_cli_subprocess_no_backend_fails(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [sys.executable, "-m", "slg.sim.evaluate"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("usage:", proc.stderr)

    # 19: Environment secret key never leaks into output or files
    def test_cli_no_leak_of_fake_api_key(self):
        fake_key = "sk-test-secret-123456"
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        env["FAKE_API_KEY"] = fake_key

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "rep.md")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "slg.sim.evaluate",
                    "--demo",
                    "--seeds",
                    "0",
                    "--turns",
                    "2",
                    "--api-key-env",
                    "FAKE_API_KEY",
                    "--out",
                    out_path,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)

            # Check stdout and stderr
            self.assertNotIn(fake_key, proc.stdout)
            self.assertNotIn(fake_key, proc.stderr)
            self.assertNotIn("Authorization", proc.stdout)

            # Check markdown file
            with open(out_path, "r", encoding="utf-8") as f:
                md_content = f.read()
            self.assertNotIn(fake_key, md_content)
            self.assertNotIn("Authorization", md_content)

            # Check json file
            json_path = out_path + ".json"
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    json_content = f.read()
                self.assertNotIn(fake_key, json_content)
                self.assertNotIn("Authorization", json_content)

    # 20: build_completer unit tests
    def test_build_completer_helper(self):
        args_demo = argparse.Namespace(demo=True, command=None, openai_base_url=None, model=None)
        self.assertIsInstance(build_completer(args_demo), DemoCompleter)

        args_cmd = argparse.Namespace(demo=False, command=["echo", "1"], openai_base_url=None, model=None)
        self.assertIsInstance(build_completer(args_cmd), CommandCompleter)

        args_openai = argparse.Namespace(
            demo=False,
            command=None,
            openai_base_url="http://localhost:1234",
            model="gpt-4o",
            api_key_env="KEY",
        )
        self.assertIsInstance(build_completer(args_openai), OpenAIChatCompleter)

        args_none = argparse.Namespace(demo=False, command=None, openai_base_url=None, model=None)
        self.assertIsNone(build_completer(args_none))


if __name__ == "__main__":
    unittest.main()
