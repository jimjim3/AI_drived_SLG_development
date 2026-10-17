"""The optional siege verdict is presentation only: off by default, thresholds fixed, scripted agent sees it when on."""
import json
import unittest

from slg.agents.backends import ScriptedCompleter
from slg.agents.llm_agent import (
    SIEGE_BAD, SIEGE_RISKY, SIEGE_VERDICT_NOTE, SYSTEM_PROMPT, LLMFactionAgent, build_user_prompt, siege_verdict,
)
from slg.engine.initial_state import build_initial_state
from slg.engine.view import build_faction_view


class TestSiegeVerdict(unittest.TestCase):
    def setUp(self):
        self.view = build_faction_view(build_initial_state("default"), "faction_1", cast_ids=["xun_yu"])

    def test_thresholds(self):
        self.assertEqual(siege_verdict(0.0), "不建議")
        self.assertEqual(siege_verdict(SIEGE_BAD - 0.01), "不建議")
        self.assertEqual(siege_verdict(SIEGE_BAD), "冒險")
        self.assertEqual(siege_verdict(SIEGE_RISKY - 0.01), "冒險")
        self.assertEqual(siege_verdict(SIEGE_RISKY), "可行")
        self.assertEqual(siege_verdict(99.0), "可行")

    def test_prompt_is_unchanged_by_default(self):
        self.assertEqual(build_user_prompt(self.view), build_user_prompt(self.view, with_verdict=False))
        self.assertNotIn("siege_verdict", build_user_prompt(self.view))

    def test_prompt_adds_verdict_per_target_when_enabled(self):
        data = json.loads(build_user_prompt(self.view, with_verdict=True).split("狀態：", 1)[1])
        officer = next(c for c in data["cast"] if c["id"] == "xun_yu")
        self.assertEqual(set(officer["siege_verdict"]), set(officer["siege_odds"]))
        for target, ratio in officer["siege_odds"].items():
            self.assertEqual(officer["siege_verdict"][target], siege_verdict(ratio))

    def test_does_not_mutate_the_view(self):
        build_user_prompt(self.view, with_verdict=True)
        self.assertNotIn("siege_verdict", next(c for c in self.view.cast if c["id"] == "xun_yu"))

    def test_agent_flag_controls_system_prompt_and_user_prompt(self):
        reply = '{"orders":[],"chronicle":"","next_cast":[]}'
        for flag in (False, True):
            comp = ScriptedCompleter([reply])
            LLMFactionAgent(comp, siege_verdict=flag).decide(self.view)
            system, user = comp.calls[0]
            self.assertEqual(system, SYSTEM_PROMPT + (SIEGE_VERDICT_NOTE if flag else ""))
            self.assertEqual("siege_verdict" in user, flag)


if __name__ == "__main__":
    unittest.main()
