"""Tests for replay determinism with disobedience, defection, and delegation."""

import random
import unittest
from dataclasses import replace

from slg.agents.base import AgentError, FactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.schema import (
    DEFECT_REJOIN_LOYALTY,
    AgentDecision,
    FactionPlan,
    FactionTurnLog,
    LegalAction,
    OfficerState,
)
from slg.sim.headless import run_headless
from slg.sim.replay import ReplayDelegateAgent, ReplayFactionAgent, replay


class MixedScriptedAgent(FactionAgent):
    """FactionAgent that gives orders for a subset of officers; others are delegated."""

    def __init__(self, orders_per_turn):
        self._orders_per_turn = orders_per_turn

    def decide(self, view):
        orders = self._orders_per_turn.get(view.turn, ())
        return FactionPlan(orders=orders)


class TestLoyaltyReplay(unittest.TestCase):
    def test_replay_delegate_agent_missing_record_raises_agent_error(self):
        # When an officer decision is not found in the replay log for that turn,
        # ReplayDelegateAgent.decide must raise AgentError.
        log = FactionTurnLog(
            turn=1,
            faction_id="faction_1",
            agent_name="test",
            executed=(AgentDecision("xun_yu", "develop_agri"),),
        )
        agent = ReplayDelegateAgent([log])
        self.assertEqual(agent.name, "replay_delegate")

        state = replace(build_initial_state(), turn=1)
        officer = state.officer("xun_yu")
        legal = [LegalAction("develop_agri")]

        # Found record
        dec = agent.decide(state, officer, legal)
        self.assertEqual(dec.action, "develop_agri")

        # Missing turn 2
        state_t2 = replace(state, turn=2)
        with self.assertRaises(AgentError):
            agent.decide(state_t2, officer, legal)

        # Missing officer
        officer_other = state.officer("xiahou_dun")
        with self.assertRaises(AgentError):
            agent.decide(state, officer_other, legal)

    def test_replay_with_disobey_defection_delegation_exact_match(self):
        # A mixed game starting from initial state with:
        # 1. An officer who disobeys (ma_chao ordered on turn 14 when loyalty < 50)
        # 2. Officers who defect (e.g. guan_yu / zhuge_liang when loyalty < 35)
        # 3. Un-ordered officers who are delegated
        from slg.agents.backends import _parse_legal_str

        class DisobeyAndDefectAgent(FactionAgent):
            def decide(self, view):
                orders = []
                if view.turn == 14:
                    for c in view.cast:
                        if c["id"] == "ma_chao":
                            for lstr in c["legal"]:
                                act, params = _parse_legal_str(lstr)
                                if act != "rest":
                                    orders.append(AgentDecision("ma_chao", act, params))
                                    break
                return FactionPlan(orders=tuple(orders))

        agents = {
            "faction_1": RuleBasedAgent("balanced"),
            "faction_2": DisobeyAndDefectAgent(),
            "faction_3": RuleBasedAgent("balanced"),
        }

        # Run headless with seed 4 for 20 turns
        orig = run_headless(seed=4, turns=20, agents_by_faction=agents)

        # Confirm there were disobey, defection, and delegation
        self.assertGreater(orig.stats["disobeyed"], 0, "Should have disobedience")
        self.assertGreater(orig.stats["delegated"], 0, "Should have delegation")
        self.assertGreater(len(orig.incidents), 0, "Should have defection incident")

        # Now replay
        replayed = replay(orig.log)

        # Exact match verification
        self.assertEqual(replayed.final_state, orig.final_state)
        self.assertEqual(replayed.events, orig.events)
        self.assertEqual(replayed.incidents, orig.incidents)
        self.assertEqual(replayed.winner, orig.winner)

    def test_replay_tampered_log_fails_equality(self):
        # Discriminative test: tampering with the seed causes divergence
        orig = run_headless(seed=12, turns=6)
        tampered = replace(orig.log, seed=99999)
        replayed = replay(tampered)
        self.assertNotEqual(replayed.events, orig.events)
        self.assertNotEqual(replayed.final_state, orig.final_state)

    def test_replay_delegate_agent_success(self):
        dec1 = AgentDecision("xun_yu", "develop_agri")
        dec2 = AgentDecision("xiahou_dun", "recruit", {"troops": 200})
        log = FactionTurnLog(
            turn=3,
            faction_id="faction_1",
            agent_name="test",
            executed=(dec1, dec2),
        )
        agent = ReplayDelegateAgent([log])
        state = replace(build_initial_state(), turn=3)
        legal = [LegalAction("develop_agri")]

        res1 = agent.decide(state, state.officer("xun_yu"), legal)
        self.assertEqual(res1, dec1)
        res2 = agent.decide(state, state.officer("xiahou_dun"), legal)
        self.assertEqual(res2, dec2)

    def test_replay_mixed_faction_and_rule_based_exact_match(self):
        # Game with faction_1 as FactionAgent and faction_2, faction_3 as RuleBasedAgent
        from slg.schema import AgentDecision, FactionPlan
        class SimpleOrdersAgent(FactionAgent):
            def decide(self, view):
                if view.turn == 1:
                    return FactionPlan(orders=(AgentDecision("xun_yu", "develop_agri"),))
                return FactionPlan()

        agents = {
            "faction_1": SimpleOrdersAgent(),
            "faction_2": RuleBasedAgent("balanced"),
            "faction_3": RuleBasedAgent("turtle"),
        }
        orig = run_headless(seed=7, turns=8, agents_by_faction=agents)
        replayed = replay(orig.log)
        self.assertEqual(replayed.final_state, orig.final_state)
        self.assertEqual(replayed.events, orig.events)
        self.assertEqual(replayed.incidents, orig.incidents)
        self.assertEqual(replayed.winner, orig.winner)


if __name__ == "__main__":
    unittest.main()
