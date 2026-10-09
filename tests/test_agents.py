import random
import unittest

from slg.engine.legal_actions import generate_legal_actions
from slg.engine.initial_state import build_initial_state
from slg.engine.validation import validate_decision
from slg.agents.random_agent import RandomAgent
from slg.agents.rule_based import RuleBasedAgent


class AgentTests(unittest.TestCase):
    def test_rule_based_returns_legal_decision_for_all_officers(self):
        state = build_initial_state()
        agent = RuleBasedAgent()
        for oid in sorted(state.officers):
            officer = state.officer(oid)
            legal = generate_legal_actions(state, officer)
            decision = agent.decide(state, officer, legal)
            ok, reason = validate_decision(state, officer, decision)
            self.assertTrue(ok, reason)

    def test_random_agent_returns_legal_decisions(self):
        state = build_initial_state()
        officer_ids = sorted(state.officers)
        for seed in range(5):
            agent = RandomAgent(random.Random(seed))
            picker = random.Random(seed + 1000)
            for _ in range(50):
                officer = state.officer(picker.choice(officer_ids))
                legal = generate_legal_actions(state, officer)
                decision = agent.decide(state, officer, legal)
                ok, reason = validate_decision(state, officer, decision)
                self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
