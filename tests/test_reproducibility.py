import random
import unittest

from slg.agents.random_agent import RandomAgent
from slg.engine.initial_state import build_initial_state
from slg.sim.headless import run_headless


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_same_result(self):
        r1 = run_headless(seed=123, turns=20)
        r2 = run_headless(seed=123, turns=20)
        self.assertEqual(r1.final_state, r2.final_state)
        self.assertEqual(r1.events, r2.events)
        self.assertEqual(r1.stats, r2.stats)
        self.assertEqual(r1.winner, r2.winner)
        self.assertIsNotNone(r1.log)
        self.assertEqual(r1.log, r2.log)
        self.assertGreater(len(r1.log.entries), 0)

    def test_initial_state_not_mutated(self):
        before = build_initial_state()
        run_headless(seed=123, turns=20)
        after = build_initial_state()
        self.assertEqual(before, after)

    def test_random_agents_same_seed_same_result(self):
        def make_agents():
            base = build_initial_state()
            return {
                fid: RandomAgent(random.Random(1000 + index))
                for index, fid in enumerate(sorted(base.factions))
            }

        r1 = run_headless(seed=7, turns=10, agents_by_faction=make_agents())
        r2 = run_headless(seed=7, turns=10, agents_by_faction=make_agents())
        self.assertEqual(r1.final_state, r2.final_state)
        self.assertEqual(r1.events, r2.events)
        self.assertEqual(r1.stats, r2.stats)
        self.assertEqual(r1.winner, r2.winner)
        self.assertIsNotNone(r1.log)
        self.assertEqual(r1.log, r2.log)


if __name__ == "__main__":
    unittest.main()
