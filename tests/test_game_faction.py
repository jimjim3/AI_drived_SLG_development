import random
import unittest
from dataclasses import replace

from slg.agents.base import Agent, FactionAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game
from slg.engine.initial_state import build_initial_state
from slg.engine.view import FactionView
from slg.schema import AgentDecision, FactionPlan, ResolutionEvent


class DummyFactionAgent(FactionAgent):
    def __init__(self, plan_fn=None):
        self.plan_fn = plan_fn
        self.views = []

    def decide(self, view: FactionView) -> FactionPlan:
        self.views.append(view)
        if self.plan_fn is not None:
            return self.plan_fn(view)
        return FactionPlan()


class RestOfficerAgent(Agent):
    name = "rest_agent"

    def decide(self, state, officer, legal):
        return AgentDecision(officer.officer_id, "rest")


class BadOfficerAgent(Agent):
    name = "bad_agent"

    def decide(self, state, officer, legal):
        return AgentDecision(officer.officer_id, "recruit", {"troops": 999999})


class GameFactionTests(unittest.TestCase):
    def test_orders_sequential_resource_deduction(self):
        # Setup city with zero commerce to avoid income variance, exactly 600 gold
        state = build_initial_state()
        c = state.city("xuchang")
        state = replace(
            state,
            cities={
                **state.cities,
                "xuchang": replace(c, commerce=0, agriculture=0, gold=600),
            },
        )

        def plan_fn(view):
            return FactionPlan(
                orders=(
                    AgentDecision("xiahou_dun", "recruit", {"troops": 600}),
                    AgentDecision("yu_jin", "recruit", {"troops": 100}),
                )
            )

        agent = DummyFactionAgent(plan_fn)
        rest_agent = RestOfficerAgent()
        agents = {
            "faction_1": agent,
            "faction_2": DummyFactionAgent(),
            "faction_3": DummyFactionAgent(),
        }
        game = Game(state, agents, random.Random(42), delegate_agent=rest_agent)
        game.step()

        self.assertEqual(game.stats["orders"], 1)
        self.assertEqual(game.stats["orders_rejected"], 1)
        # First order succeeded: 600 gold deducted, troops increased by 600
        new_city = game.state.city("xuchang")
        self.assertEqual(new_city.gold, 0)
        self.assertEqual(new_city.troops, c.troops + 600)

        # Check rejection log
        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertEqual(len(log.rejected), 1)
        self.assertEqual(log.rejected[0][0], "yu_jin")
        self.assertEqual(log.rejected[0][1], "recruit")

    def test_duplicate_officer_order_rejected(self):
        def plan_fn(view):
            return FactionPlan(
                orders=(
                    AgentDecision("xun_yu", "develop_agri"),
                    AgentDecision("xun_yu", "develop_commerce"),
                )
            )

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["orders"], 1)
        self.assertEqual(game.stats["orders_rejected"], 1)
        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertEqual(len(log.rejected), 1)
        self.assertEqual(log.rejected[0][0], "xun_yu")
        self.assertIn("already acted", log.rejected[0][2])

    def test_nonexistent_officer_rejected(self):
        def plan_fn(view):
            return FactionPlan(
                orders=(AgentDecision("ghost_officer", "develop_agri"),)
            )

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["orders"], 0)
        self.assertEqual(game.stats["orders_rejected"], 1)
        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertEqual(log.rejected[0][0], "ghost_officer")
        self.assertIn("not found", log.rejected[0][2])

    def test_other_faction_officer_rejected(self):
        def plan_fn(view):
            # guan_yu belongs to faction_2
            return FactionPlan(orders=(AgentDecision("guan_yu", "develop_agri"),))

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["orders"], 0)
        self.assertEqual(game.stats["orders_rejected"], 1)
        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertEqual(log.rejected[0][0], "guan_yu")
        self.assertIn("not in faction", log.rejected[0][2])

    def test_dead_officer_rejected(self):
        state = build_initial_state()
        state = replace(
            state,
            officers={
                **state.officers,
                "xun_yu": replace(state.officer("xun_yu"), is_alive=False),
            },
        )

        def plan_fn(view):
            return FactionPlan(orders=(AgentDecision("xun_yu", "develop_agri"),))

        agent = DummyFactionAgent(plan_fn)
        game = Game(state, {"faction_1": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["orders"], 0)
        self.assertEqual(game.stats["orders_rejected"], 1)
        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertEqual(log.rejected[0][0], "xun_yu")
        self.assertIn("not alive", log.rejected[0][2])

    def test_illegal_param_rejected_and_feedback_next_turn(self):
        views = []

        def plan_fn(view):
            views.append(view)
            if view.turn == 1:
                return FactionPlan(
                    orders=(AgentDecision("xun_yu", "recruit", {"troops": 999999}),)
                )
            return FactionPlan()

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()
        self.assertEqual(game.stats["orders_rejected"], 1)

        # Step turn 2
        game.step()
        self.assertEqual(len(views), 2)
        view_turn_2 = views[1]
        self.assertGreater(len(view_turn_2.feedback), 0)
        self.assertTrue(any("xun_yu recruit:" in fb for fb in view_turn_2.feedback))

    def test_unmentioned_officers_delegated(self):
        def plan_fn(view):
            # Only order 1 officer; faction_1 has 14 living officers total
            return FactionPlan(orders=(AgentDecision("xun_yu", "develop_agri"),))

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["orders"], 1)
        self.assertEqual(game.stats["delegated"], 13)
        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertEqual(len(log.delegated), 13)
        self.assertNotIn("xun_yu", log.delegated)
        self.assertEqual(len(log.executed), 14)

    def test_agent_raises_exception_full_delegation_game_continues(self):
        class ExplodingAgent(FactionAgent):
            name = "exploding"

            def decide(self, view):
                raise RuntimeError("LLM exploded")

        agent = ExplodingAgent()
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()

        self.assertEqual(game.stats["plan_failures"], 1)
        self.assertEqual(game.stats["orders"], 0)
        self.assertEqual(game.stats["delegated"], 14)
        self.assertEqual(game.stats["valid"], game.stats["decisions"])

        log = [l for l in game.faction_logs if l.faction_id == "faction_1"][0]
        self.assertTrue(log.plan_failed)
        self.assertEqual(len(log.delegated), 14)
        self.assertEqual(len(log.executed), 14)

        # Game can continue to next turn
        game.step()
        self.assertEqual(game.state.turn, 2)
        self.assertEqual(game.stats["plan_failures"], 2)

    def test_valid_equals_decisions_invariant(self):
        def plan_fn(view):
            return FactionPlan(
                orders=(
                    AgentDecision("xun_yu", "develop_agri"),
                    AgentDecision("xun_yu", "develop_agri"),  # duplicate
                    AgentDecision("ghost_officer", "recruit"),  # nonexistent
                    AgentDecision("xiahou_dun", "recruit", {"troops": 999999}),  # invalid param
                )
            )

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        for _ in range(5):
            game.step()
            self.assertEqual(game.stats["valid"], game.stats["decisions"])

    def test_next_cast_affects_next_turn_view(self):
        # dian_wei is a low-stat officer (sum=185), not included in default cast (limit 6)
        # Check that without next_cast, dian_wei is not in cast
        initial_view_agent = DummyFactionAgent()
        g0 = Game(build_initial_state(), {"faction_1": initial_view_agent}, random.Random(42))
        g0.step()
        t1_cast = [c["id"] for c in initial_view_agent.views[0].cast]
        self.assertNotIn("dian_wei", t1_cast)

        # Now test that returning next_cast=("dian_wei",) brings dian_wei into turn 2 cast
        def plan_fn(view):
            return FactionPlan(next_cast=("dian_wei",))

        agent = DummyFactionAgent(plan_fn)
        g1 = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        g1.step()
        g1.step()
        t2_cast = [c["id"] for c in agent.views[1].cast]
        self.assertIn("dian_wei", t2_cast)

    def test_forced_cast_on_siege(self):
        # dian_wei is in xuchang with stats=185, normally not in cast
        # In turn 1, create a resolution event representing an enemy siege on xuchang
        agent = DummyFactionAgent()
        game = Game(build_initial_state(), {"faction_1": agent}, random.Random(42))
        game.step()  # turn 1

        # Turn 1 cast does not have dian_wei
        self.assertNotIn("dian_wei", [c["id"] for c in agent.views[0].cast])

        # Synthesize enemy siege event on xuchang in turn 1
        game.events.append(
            ResolutionEvent(
                turn=1,
                officer_id="guan_yu",
                faction_id="faction_2",
                action="siege",
                city_id="xuchang",
                detail="siege xuchang",
            )
        )

        game.step()  # turn 2
        # Turn 2 cast MUST contain dian_wei because of forced_cast
        t2_cast = [c["id"] for c in agent.views[1].cast]
        self.assertIn("dian_wei", t2_cast)

    def test_view_fog_of_war_and_symmetry(self):
        # Test symmetry: faction_2 receives FactionView whose to_dict has standard keys
        # and non-adjacent enemy city (jianye) is NOT present in cities or frontier
        received_views = []

        def plan_fn(view):
            received_views.append(view)
            return FactionPlan()

        agent = DummyFactionAgent(plan_fn)
        game = Game(build_initial_state(), {"faction_2": agent}, random.Random(42))
        game.step()

        self.assertEqual(len(received_views), 1)
        view = received_views[0]
        self.assertIsInstance(view, FactionView)

        data = view.to_dict()
        expected_keys = {
            "turn",
            "faction_id",
            "faction_name",
            "cities",
            "frontier",
            "cast",
            "roster",
            "events",
            "feedback",
        }
        self.assertEqual(set(data.keys()), expected_keys)

        # Fog of war: jianye is not adjacent to luoyang
        city_ids_in_view = {c["id"] for c in data["cities"]} | {f["id"] for f in data["frontier"]}
        self.assertNotIn("jianye", city_ids_in_view)

    def test_officer_agent_backward_compatibility(self):
        agents = {
            "faction_1": RuleBasedAgent("balanced"),
            "faction_2": BadOfficerAgent(),
            "faction_3": RuleBasedAgent("turtle"),
        }
        game = Game(build_initial_state(), agents, random.Random(42))
        game.step()

        self.assertEqual(game.stats["valid"], game.stats["decisions"])
        self.assertGreater(game.stats["rejected"], 0)  # BadOfficerAgent was rejected & fell back
        self.assertGreater(game.stats["fallbacks"], 0)

        # FactionTurnLog still written for all factions
        fids = [log.faction_id for log in game.faction_logs]
        self.assertEqual(set(fids), {"faction_1", "faction_2", "faction_3"})
        for flog in game.faction_logs:
            self.assertGreater(len(flog.executed), 0)
            self.assertEqual(flog.chronicle, "")
            self.assertEqual(flog.rejected, ())
            self.assertEqual(flog.delegated, ())
            self.assertFalse(flog.plan_failed)

    def test_mixed_agents(self):
        # faction_1 uses FactionAgent, faction_2 uses RuleBasedAgent
        f1_agent = DummyFactionAgent(
            lambda v: FactionPlan(orders=(AgentDecision("xun_yu", "develop_agri"),))
        )
        agents = {
            "faction_1": f1_agent,
            "faction_2": RuleBasedAgent("balanced"),
            "faction_3": RuleBasedAgent("balanced"),
        }
        game = Game(build_initial_state(), agents, random.Random(42))
        game.step()

        self.assertEqual(game.stats["valid"], game.stats["decisions"])
        self.assertEqual(game.stats["orders"], 1)
        self.assertEqual(game.stats["delegated"], 13)

        # Logs should record correct sources
        f1_entries = [e for e in game.log_entries if e.faction_id == "faction_1"]
        f1_sources = {e.source for e in f1_entries}
        self.assertEqual(f1_sources, {"order", "delegate"})

        f2_entries = [e for e in game.log_entries if e.faction_id == "faction_2"]
        f2_sources = {e.source for e in f2_entries}
        self.assertEqual(f2_sources, {"agent"})


if __name__ == "__main__":
    unittest.main()
