import random
import unittest
from dataclasses import replace

from slg.agents.backends import DemoCompleter
from slg.agents.base import AgentError, FactionAgent
from slg.agents.llm_agent import LLMFactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.view import build_faction_view
from slg.schema import AgentDecision, FactionPlan, FactionTurnLog, TurnLog
from slg.sim.headless import run_headless
from slg.sim.replay import ReplayFactionAgent, replay


class ScriptedOrdersAgent(FactionAgent):
    def __init__(self, orders_per_turn):
        self.orders_per_turn = orders_per_turn

    def decide(self, view):
        orders = self.orders_per_turn.get(view.turn, ())
        return FactionPlan(orders=orders, chronicle=f"T{view.turn} plan")


class ReplayFactionTests(unittest.TestCase):
    def test_replay_rule_based_game_exact_match(self):
        # 10-turn rule-based game (all factions use Agent level RuleBasedAgent)
        orig = run_headless(seed=42, turns=10)
        replayed = replay(orig.log)

        self.assertEqual(replayed.final_state, orig.final_state)
        self.assertEqual(replayed.events, orig.events)
        self.assertEqual(replayed.winner, orig.winner)
        self.assertGreater(len(replayed.events), 0)

    def test_replay_demo_completer_game_exact_match(self):
        # 10-turn all LLMFactionAgent(DemoCompleter()) game
        state = build_initial_state()
        agents = {fid: LLMFactionAgent(DemoCompleter()) for fid in state.factions}
        orig = run_headless(seed=101, turns=10, agents_by_faction=agents)
        replayed = replay(orig.log)

        self.assertEqual(replayed.final_state, orig.final_state)
        self.assertEqual(replayed.events, orig.events)
        self.assertEqual(replayed.winner, orig.winner)
        self.assertGreater(len(replayed.events), 0)

    def test_replay_with_rejected_orders_and_delegation_exact_match(self):
        # Game with valid orders, rejected orders, and delegation
        orders_f1 = {
            1: (
                AgentDecision("xun_yu", "develop_agri"),  # valid
                AgentDecision("xun_yu", "develop_commerce"),  # duplicate -> rejected
                AgentDecision("xiahou_dun", "recruit", {"troops": 999999}),  # illegal -> rejected
                # other 6 officers of faction_1 not mentioned -> delegated!
            ),
            2: (
                AgentDecision("dian_wei", "recruit", {"troops": 100}),  # valid
                AgentDecision("ghost_officer", "develop_agri"),  # nonexistent -> rejected
            ),
        }
        agent_f1 = ScriptedOrdersAgent(orders_f1)
        agents = {
            "faction_1": agent_f1,
            "faction_2": RuleBasedAgent("balanced"),
            "faction_3": RuleBasedAgent("balanced"),
        }

        orig = run_headless(seed=77, turns=4, agents_by_faction=agents)

        # Confirm there were both rejections and delegations
        total_rejected = sum(len(fl.rejected) for fl in orig.log.faction_logs)
        total_delegated = sum(len(fl.delegated) for fl in orig.log.faction_logs)
        self.assertGreater(total_rejected, 0)
        self.assertGreater(total_delegated, 0)

        # Replay must match exactly
        replayed = replay(orig.log)
        self.assertEqual(replayed.final_state, orig.final_state)
        self.assertEqual(replayed.events, orig.events)
        self.assertEqual(replayed.winner, orig.winner)

    def test_replay_missing_record_raises_agent_error(self):
        orig = run_headless(seed=42, turns=4)
        # Remove turn 2 logs for faction_1
        tampered_logs = tuple(
            fl for fl in orig.log.faction_logs if not (fl.turn == 2 and fl.faction_id == "faction_1")
        )
        tampered_log = replace(orig.log, faction_logs=tampered_logs)

        with self.assertRaises(AgentError):
            replay(tampered_log)

    def test_replay_faction_agent_unit(self):
        log1 = FactionTurnLog(
            turn=1,
            faction_id="faction_1",
            agent_name="test",
            executed=(AgentDecision("xun_yu", "develop_agri"),),
        )
        agent = ReplayFactionAgent([log1])
        self.assertEqual(agent.name, "replay")

        state = replace(build_initial_state(), turn=1)
        view_valid = build_faction_view(state, "faction_1", cast_ids=("xun_yu",))
        plan = agent.decide(view_valid)
        self.assertEqual(plan.orders, log1.executed)

        # Missing record
        view_missing = build_faction_view(replace(state, turn=2), "faction_1", cast_ids=("xun_yu",))
        with self.assertRaises(AgentError):
            agent.decide(view_missing)

    def test_replay_discriminative_divergence_fails_equality(self):
        orig = run_headless(seed=42, turns=10)
        # Replaying with a different seed in log should produce different final_state/events
        tampered_log = replace(orig.log, seed=999999)
        replayed = replay(tampered_log)
        self.assertNotEqual(replayed.events, orig.events)


if __name__ == "__main__":
    unittest.main()
