import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

from slg.agents.backends import DemoCompleter, _parse_legal_str
from slg.agents.llm_agent import LLMFactionAgent, build_user_prompt, parse_plan
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.view import build_faction_view, select_cast
from slg.sim.headless import run_headless


class RunLLMTests(unittest.TestCase):
    def test_gameresult_usage_keys_and_counts(self):
        # 5 turns, 2 LLM factions, 1 RuleBasedAgent
        agents = {
            "faction_1": LLMFactionAgent(DemoCompleter()),
            "faction_2": LLMFactionAgent(DemoCompleter()),
            "faction_3": RuleBasedAgent("balanced"),
        }
        result = run_headless(seed=42, turns=5, agents_by_faction=agents)

        # Only factions with usage attribute should be in result.usage
        self.assertEqual(set(result.usage.keys()), {"faction_1", "faction_2"})
        # Each LLM faction should have been called 5 times
        self.assertEqual(result.usage["faction_1"]["calls"], 5)
        self.assertEqual(result.usage["faction_2"]["calls"], 5)
        self.assertGreater(result.usage["faction_1"]["prompt_chars"], 0)
        self.assertGreater(result.usage["faction_1"]["response_chars"], 0)
        self.assertEqual(result.usage["faction_1"]["parse_failures"], 0)
        self.assertEqual(result.usage["faction_1"]["errors"], 0)

    def test_demo_completer_output_parseable_and_zero_rejections(self):
        state = build_initial_state()
        cast = select_cast(state, "faction_1")
        view = build_faction_view(state, "faction_1", cast)
        user_prompt = build_user_prompt(view)

        completer = DemoCompleter()
        raw_output = completer("system_prompt", user_prompt)

        plan = parse_plan(raw_output)
        self.assertGreater(len(plan.orders), 0)
        self.assertTrue(plan.chronicle.startswith("第0回合，曹操") or plan.chronicle.startswith("第"))
        self.assertEqual(plan.next_cast, cast)

        # Run with Game to ensure zero rejections
        agent = LLMFactionAgent(completer)
        game = Game(state, {"faction_1": agent, "faction_2": agent, "faction_3": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["orders_rejected"], 0)
        self.assertGreater(game.stats["orders"], 0)

    def test_20_turns_full_demo_completer_valid_equals_decisions(self):
        state = build_initial_state()
        agents = {fid: LLMFactionAgent(DemoCompleter()) for fid in state.factions}
        result = run_headless(seed=42, turns=20, agents_by_faction=agents)

        self.assertEqual(result.stats["valid"], result.stats["decisions"])
        self.assertEqual(len(result.events), result.stats["decisions"])
        # Demo orders can contend for the same city's gold as the roster grows;
        # require that rejections stay a small minority rather than pinning a count.
        total = result.stats["orders"] + result.stats["orders_rejected"]
        self.assertGreater(result.stats["orders"], 0)
        self.assertLess(result.stats["orders_rejected"], 0.1 * total)

    def test_parse_legal_str_parsing(self):
        # Numeric min..max/step
        act, params = _parse_legal_str("recruit troops=100..1200/100")
        self.assertEqual(act, "recruit")
        self.assertEqual(params, {"troops": 100})

        # Discrete choices
        act, params = _parse_legal_str("move to=[chenliu,xiangyang]")
        self.assertEqual(act, "move")
        self.assertEqual(params, {"to": "chenliu"})

        # Multiple params: discrete + numeric
        act, params = _parse_legal_str("siege to=[luoyang,xuchang] troops=500..900/100")
        self.assertEqual(act, "siege")
        self.assertEqual(params, {"to": "luoyang", "troops": 500})

        # No params
        act, params = _parse_legal_str("develop_agri")
        self.assertEqual(act, "develop_agri")
        self.assertEqual(params, {})

    def test_cli_subprocess_demo_turns_5(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [sys.executable, "-m", "slg.sim.run_llm", "--demo", "--turns", "5", "--seed", "42"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, f"CLI stderr: {proc.stderr}")
        self.assertIn("winner:", proc.stdout)
        self.assertIn("stats:", proc.stdout)
        self.assertIn("usage:", proc.stdout)
        self.assertIn("estimated tokens:", proc.stdout)

    def test_cli_subprocess_no_backend_fails(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [sys.executable, "-m", "slg.sim.run_llm"],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("usage:", proc.stderr)

    def test_cli_subprocess_save_log(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "slg.sim.run_llm",
                    "--demo",
                    "--turns",
                    "2",
                    "--seed",
                    "7",
                    "--save-log",
                    temp_path,
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, f"CLI stderr: {proc.stderr}")
            self.assertTrue(os.path.exists(temp_path))

            with open(temp_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            self.assertEqual(saved["seed"], 7)
            self.assertEqual(saved["turns"], 2)
            self.assertIn("faction_logs", saved)
            self.assertGreater(len(saved["faction_logs"]), 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_cli_subprocess_multiple_llm_factions(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = "src"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "slg.sim.run_llm",
                "--demo",
                "--turns",
                "3",
                "--llm-faction",
                "faction_1",
                "--llm-faction",
                "faction_2",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, f"CLI stderr: {proc.stderr}")
        self.assertIn("[faction_1] usage:", proc.stdout)
        self.assertIn("[faction_2] usage:", proc.stdout)


if __name__ == "__main__":
    import random
    unittest.main()
