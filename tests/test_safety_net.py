import random
import unittest

from slg.agents.base import Agent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.schema import AgentDecision


class BadAgent(Agent):
    def decide(self, state, officer, legal):
        return AgentDecision(officer.officer_id, "recruit", {"troops": 999999})


class SafetyNetTests(unittest.TestCase):
    def test_fallback_completes_game(self):
        state = build_initial_state()
        agents = {fid: BadAgent() for fid in state.factions}
        game = Game(state, agents, random.Random(42))
        final = game.run(10)
        self.assertEqual(final.turn, 10)
        self.assertEqual(game.stats["valid"], game.stats["decisions"])
        self.assertGreater(game.stats["decisions"], 0)
        self.assertGreater(game.stats["fallbacks"], 0)
        self.assertGreater(game.stats["rejected"], 0)


if __name__ == "__main__":
    unittest.main()
