"""Tests for rules v2 (map adjacency, food upkeep, variable siege, rule styles)."""

import random
import sys
from pathlib import Path
import unittest
from dataclasses import replace

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from slg.agents.random_agent import RandomAgent
from slg.agents.rule_based import RuleBasedAgent
from slg.engine.game import Game, apply_income, compute_winner, update_faction_status
from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.resolution import resolve_decision
from slg.engine.validation import validate_decision
from slg.schema import AgentDecision, CityState, GameState, OfficerState


class FixedUniformRng:
    """RNG stub: uniform() always returns a fixed value for exact arithmetic verification."""

    def __init__(self, value: float = 1.0):
        self.value = value

    def uniform(self, a: float, b: float) -> float:
        return self.value


class RulesV2Tests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()
        self.fixed_rng = FixedUniformRng(1.0)

    # -------------------------------------------------------------------------
    # 1. Adjacency: move & siege
    # -------------------------------------------------------------------------
    def test_move_adjacent_friendly_city_is_legal(self):
        # xuchang and chenliu are adjacent friendly cities of faction_1
        officer = self.state.officer("xun_yu")
        decision = AgentDecision("xun_yu", "move", {"to": "chenliu"})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertTrue(ok, f"Expected move to adjacent friendly city to be legal: {reason}")

    def test_move_non_adjacent_friendly_city_is_rejected(self):
        # chenliu and xiangyang are both faction_1 cities, but NOT adjacent
        officer = self.state.officer("cao_ren")  # stationed at chenliu
        decision = AgentDecision("cao_ren", "move", {"to": "xiangyang"})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok, "Expected move to non-adjacent friendly city to be rejected")
        self.assertIn("choices", reason)

    def test_siege_adjacent_enemy_city_is_legal(self):
        # xuchang (faction_1) and luoyang (faction_2) are adjacent
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 500})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertTrue(ok, f"Expected siege against adjacent enemy city to be legal: {reason}")

    def test_siege_non_adjacent_enemy_city_is_rejected(self):
        # xuchang (faction_1) and jianye (faction_3) are enemy cities, but NOT adjacent
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "jianye", "troops": 500})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok, "Expected siege against non-adjacent enemy city to be rejected")
        self.assertIn("choices", reason)

    # -------------------------------------------------------------------------
    # 2. Income reproducibility & seed variation
    # -------------------------------------------------------------------------
    def test_income_reproducible_with_same_seed(self):
        state1 = apply_income(self.state, random.Random(12345))
        state2 = apply_income(self.state, random.Random(12345))
        self.assertEqual(state1.cities, state2.cities)

    def test_income_differs_with_different_seed(self):
        state1 = apply_income(self.state, random.Random(12345))
        state2 = apply_income(self.state, random.Random(67890))
        diff_cities = [
            cid for cid in self.state.cities
            if state1.city(cid).gold != state2.city(cid).gold
            or state1.city(cid).food != state2.city(cid).food
        ]
        self.assertGreater(len(diff_cities), 0, "Different RNG seeds must produce different income")

    # -------------------------------------------------------------------------
    # 3. Famine (food shortage and garrison desertion)
    # -------------------------------------------------------------------------
    def test_famine_depletes_food_and_causes_desertion(self):
        # Craft a city where food runs into negative during upkeep:
        # agriculture=0, food=0, troops=1000 -> upkeep needs 100 food -> food < 0
        starving_city = replace(
            self.state.city("xuchang"),
            agriculture=0,
            food=0,
            troops=1000,
        )
        custom_state = replace(
            self.state,
            cities={**self.state.cities, "xuchang": starving_city},
        )
        result_state = apply_income(custom_state, random.Random(42))
        res_city = result_state.city("xuchang")
        self.assertEqual(res_city.food, 0, "Famine must clamp food to 0")
        self.assertEqual(res_city.troops, 1000 * 9 // 10, "Famine must reduce troops to troops * 9 // 10")

    def test_sufficient_food_prevents_desertion(self):
        # Craft a city with abundant food: troops must remain unchanged
        wealthy_city = replace(
            self.state.city("xuchang"),
            agriculture=500,
            food=5000,
            troops=1000,
        )
        custom_state = replace(
            self.state,
            cities={**self.state.cities, "xuchang": wealthy_city},
        )
        result_state = apply_income(custom_state, random.Random(42))
        res_city = result_state.city("xuchang")
        self.assertGreater(res_city.food, 0)
        self.assertEqual(res_city.troops, 1000, "Well-fed garrison must not suffer desertion")

    # -------------------------------------------------------------------------
    # 4. Upkeep formula verification
    # -------------------------------------------------------------------------
    def test_upkeep_food_change_matches_formula(self):
        # With fixed rf = 1.0, food delta == int(agriculture // 4 * 1.0) - troops // 10
        new_state = apply_income(self.state, FixedUniformRng(1.0))
        for cid, city in self.state.cities.items():
            new_city = new_state.city(cid)
            expected_delta = (city.agriculture // 4) - (city.troops // 10)
            actual_delta = new_city.food - city.food
            self.assertEqual(
                actual_delta,
                expected_delta,
                f"City {cid}: expected food delta {expected_delta}, got {actual_delta}",
            )

    # -------------------------------------------------------------------------
    # 5. Develop gain: scaling by politics & note in legal actions
    # -------------------------------------------------------------------------
    def test_develop_agriculture_gain_scales_with_politics(self):
        # Xun Yu (politics 95): gain = 50 * (50 + 95) // 100 = 72
        # Dian Wei (politics 20): gain = 50 * (50 + 20) // 100 = 35
        xun_yu = self.state.officer("xun_yu")
        dian_wei = self.state.officer("dian_wei")
        self.assertEqual(xun_yu.politics, 95)
        self.assertEqual(dian_wei.politics, 20)

        s_xun_yu, ev_xun_yu = resolve_decision(
            self.state, xun_yu, AgentDecision("xun_yu", "develop_agri", {}), self.fixed_rng
        )
        s_dian_wei, ev_dian_wei = resolve_decision(
            self.state, dian_wei, AgentDecision("dian_wei", "develop_agri", {}), self.fixed_rng
        )

        gain_xun_yu = s_xun_yu.city("xuchang").agriculture - self.state.city("xuchang").agriculture
        gain_dian_wei = s_dian_wei.city("xuchang").agriculture - self.state.city("xuchang").agriculture

        self.assertEqual(gain_xun_yu, 50 * 145 // 100)
        self.assertEqual(gain_xun_yu, 72)
        self.assertEqual(gain_dian_wei, 50 * 70 // 100)
        self.assertEqual(gain_dian_wei, 35)
        self.assertNotEqual(gain_xun_yu, gain_dian_wei)

    def test_develop_legal_action_note_contains_actual_gain(self):
        xun_yu = self.state.officer("xun_yu")
        dian_wei = self.state.officer("dian_wei")
        la_xun_yu = {la.action: la for la in generate_legal_actions(self.state, xun_yu)}
        la_dian_wei = {la.action: la for la in generate_legal_actions(self.state, dian_wei)}

        self.assertIn("+72", la_xun_yu["develop_agri"].note)
        self.assertIn("+35", la_dian_wei["develop_agri"].note)

    # -------------------------------------------------------------------------
    # 6. Siege troops boundary conditions
    # -------------------------------------------------------------------------
    def test_siege_troops_min_boundary_valid(self):
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 500})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertTrue(ok, reason)

    def test_siege_troops_below_min_rejected(self):
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 499})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok, "Troops below 500 must be rejected")

    def test_siege_troops_off_step_rejected(self):
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 550})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok, "Troops not on step 100 must be rejected")

    def test_siege_troops_max_boundary_valid(self):
        # xuchang troops = 1000. max = ((1000 - 100) // 100) * 100 = 900
        officer = self.state.officer("xiahou_dun")
        city = self.state.city("xuchang")
        max_troops = ((city.troops - 100) // 100) * 100
        self.assertEqual(max_troops, 900)
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": max_troops})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertTrue(ok, reason)

    def test_siege_troops_exceeding_max_rejected(self):
        # max + 100 = 1000 leaves no minimum garrison (100)
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 1000})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok, "Troops exceeding maximum garrison allowance must be rejected")

    def test_siege_missing_troops_param_rejected(self):
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang"})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok)
        self.assertIn("missing required param 'troops'", reason)

    def test_siege_missing_to_param_rejected(self):
        officer = self.state.officer("xiahou_dun")
        decision = AgentDecision("xiahou_dun", "siege", {"troops": 500})
        ok, reason = validate_decision(self.state, officer, decision)
        self.assertFalse(ok)
        self.assertIn("missing required param 'to'", reason)

    def test_siege_not_in_legal_actions_when_garrison_under_600(self):
        officer = self.state.officer("xiahou_dun")
        # City troops 599: max siege = ((599 - 100) // 100) * 100 = 400 < MIN_SIEGE_TROOPS (500)
        low_garrison_state = replace(
            self.state,
            cities={**self.state.cities, "xuchang": replace(self.state.city("xuchang"), troops=599)},
        )
        legal_actions = generate_legal_actions(low_garrison_state, officer)
        self.assertNotIn("siege", [la.action for la in legal_actions])

        # Attempting siege anyway must fail validation
        decision = AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 500})
        ok, reason = validate_decision(low_garrison_state, officer, decision)
        self.assertFalse(ok)
        self.assertIn("not legal", reason)

    # -------------------------------------------------------------------------
    # 7. Combat formula hand calculations (3 scenarios)
    # -------------------------------------------------------------------------
    def _isolate_officers(self, base_state: GameState, att_officer: OfficerState, def_officer: OfficerState) -> dict:
        """Helper to ensure only def_officer is in luoyang and att_officer is in xuchang."""
        officers = dict(base_state.officers)
        for oid, o in officers.items():
            if o.city_id == "luoyang":
                officers[oid] = replace(o, city_id="jianye", faction_id="faction_3")
        officers[att_officer.officer_id] = att_officer
        officers[def_officer.officer_id] = def_officer
        return officers

    def test_combat_formula_attacker_decisive_victory(self):
        # Attacker officer: war=80, leadership=80 -> (80+80)/200 = 0.8 -> atk = c * 1.3 * 1.0 = 1300 for c=1000
        # Defender: single officer war=50, leadership=50 -> dq=50 -> (0.5 + 50/100) = 1.0
        # Defender city: troops=200, defense=0 -> dfn = 200 * 1.0 * 1.0 * 1.0 = 200
        # atk (1300) > dfn (200) -> victory
        # loss = int(1000 * min(0.5, max(0.1, 0.4 * 200 / 1300))) = int(1000 * 0.1) = 100
        # survivors = 1000 - 100 = 900
        # origin city troops = 2000 - 1000 = 1000
        att_officer = replace(self.state.officer("xiahou_dun"), war=80, leadership=80)
        def_officer = replace(self.state.officer("guan_yu"), war=50, leadership=50)
        officers = self._isolate_officers(self.state, att_officer, def_officer)

        state = replace(
            self.state,
            officers=officers,
            cities={
                **self.state.cities,
                "xuchang": replace(self.state.city("xuchang"), troops=2000),
                "luoyang": replace(self.state.city("luoyang"), troops=200, defense=0),
            },
        )
        new_state, event = resolve_decision(
            state, att_officer, AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 1000}), self.fixed_rng
        )

        self.assertEqual(event.captured_city, "luoyang")
        self.assertEqual(new_state.city("luoyang").owner, "faction_1")
        self.assertEqual(new_state.city("luoyang").troops, 900)
        self.assertEqual(new_state.city("xuchang").troops, 1000)

    def test_combat_formula_attacker_decisive_defeat(self):
        # Attacker officer: war=50, leadership=50 -> (50+50)/200 = 0.5 -> atk = 500 * (0.5+0.5) * 1.0 = 500 for c=500
        # Defender: single officer war=50, leadership=50 -> dq=50 -> (0.5 + 50/100) = 1.0
        # Defender city: troops=2000, defense=200 -> 1 + 200/200 = 2.0 -> dfn = 2000 * 2.0 * 1.0 * 1.0 = 4000
        # atk (500) <= dfn (4000) -> repelled
        # attacker_loss = int(500 * min(0.8, max(0.3, 0.5 * 4000 / 500))) = int(500 * 0.8) = 400
        # defender_loss = int(2000 * min(0.3, 0.15 * 500 / 4000)) = int(2000 * 0.01875) = int(37.5) = 37
        # origin city troops = 1000 - 400 = 600
        # target city troops = 2000 - 37 = 1963
        att_officer = replace(self.state.officer("xiahou_dun"), war=50, leadership=50)
        def_officer = replace(self.state.officer("guan_yu"), war=50, leadership=50)
        officers = self._isolate_officers(self.state, att_officer, def_officer)

        state = replace(
            self.state,
            officers=officers,
            cities={
                **self.state.cities,
                "xuchang": replace(self.state.city("xuchang"), troops=1000),
                "luoyang": replace(self.state.city("luoyang"), troops=2000, defense=200),
            },
        )
        new_state, event = resolve_decision(
            state, att_officer, AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 500}), self.fixed_rng
        )

        self.assertIsNone(event.captured_city)
        self.assertEqual(new_state.city("luoyang").owner, "faction_2")
        self.assertEqual(new_state.city("xuchang").troops, 600)
        self.assertEqual(new_state.city("luoyang").troops, 1963)

    def test_combat_formula_close_battle(self):
        # Attacker officer: war=50, leadership=50 -> atk = 1000 * 1.0 * 1.0 = 1000 for c=1000
        # Defender: single officer war=50, leadership=50 -> dq=50 -> 1.0
        # Defender city: troops=900, defense=0 -> dfn = 900 * 1.0 * 1.0 * 1.0 = 900
        # atk (1000) > dfn (900) -> victory
        # ratio dfn/atk = 0.9 -> loss = int(1000 * min(0.5, max(0.1, 0.4 * 0.9))) = int(1000 * 0.36) = 360
        # survivors = 1000 - 360 = 640
        # origin city troops = 1500 - 1000 = 500
        att_officer = replace(self.state.officer("xiahou_dun"), war=50, leadership=50)
        def_officer = replace(self.state.officer("guan_yu"), war=50, leadership=50)
        officers = self._isolate_officers(self.state, att_officer, def_officer)

        state = replace(
            self.state,
            officers=officers,
            cities={
                **self.state.cities,
                "xuchang": replace(self.state.city("xuchang"), troops=1500),
                "luoyang": replace(self.state.city("luoyang"), troops=900, defense=0),
            },
        )
        new_state, event = resolve_decision(
            state, att_officer, AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 1000}), self.fixed_rng
        )

        self.assertEqual(event.captured_city, "luoyang")
        self.assertEqual(new_state.city("luoyang").troops, 640)
        self.assertEqual(new_state.city("xuchang").troops, 500)

    # -------------------------------------------------------------------------
    # 8. Attacker victory mechanics: city transfer & defender retreat
    # -------------------------------------------------------------------------
    def test_attacker_victory_state_transfer_and_retreat_to_smallest_city_id(self):
        # Set up faction_2 to own luoyang (target), chenliu, and xiangyang.
        # Defending officers at luoyang must retreat to the lexicographically smallest friendly city: 'chenliu'.
        cities = dict(self.state.cities)
        cities["chenliu"] = replace(cities["chenliu"], owner="faction_2")
        cities["xiangyang"] = replace(cities["xiangyang"], owner="faction_2")
        cities["xuchang"] = replace(cities["xuchang"], troops=5000)
        cities["luoyang"] = replace(cities["luoyang"], troops=100, defense=0)

        state = replace(self.state, cities=cities)
        officer = state.officer("xiahou_dun")
        c = 4000
        new_state, event = resolve_decision(
            state, officer, AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": c}), self.fixed_rng
        )

        self.assertEqual(new_state.city("luoyang").owner, "faction_1")
        # loss = int(4000 * 0.1) = 400 -> survivors = 3600
        self.assertEqual(new_state.city("luoyang").troops, 3600)

        luoyang_defenders = [
            o for o in state.officers.values()
            if o.faction_id == "faction_2" and o.city_id == "luoyang" and o.is_alive
        ]
        self.assertGreater(len(luoyang_defenders), 0)
        for def_o in luoyang_defenders:
            retreated = new_state.officer(def_o.officer_id)
            self.assertEqual(
                retreated.city_id,
                "chenliu",
                f"Defender {def_o.officer_id} must retreat to smallest friendly city id 'chenliu', got '{retreated.city_id}'",
            )
            self.assertEqual(retreated.faction_id, "faction_2")

    # -------------------------------------------------------------------------
    # 9. Faction elimination: officer capture, defection, and deactivation
    # -------------------------------------------------------------------------
    def test_faction_elimination_capture_and_defection(self):
        # In initial state, faction_2 owns only luoyang.
        # Conquering luoyang eliminates faction_2.
        cities = dict(self.state.cities)
        cities["xuchang"] = replace(cities["xuchang"], troops=5000)
        cities["luoyang"] = replace(cities["luoyang"], troops=100, defense=0)
        state = replace(self.state, cities=cities)

        officer = state.officer("xiahou_dun")
        new_state, event = resolve_decision(
            state, officer, AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 4000}), self.fixed_rng
        )

        faction_2_officers = [o for o in state.officers.values() if o.faction_id == "faction_2"]
        self.assertEqual(len(faction_2_officers), 6)
        self.assertEqual(set(event.captured_officers), {o.officer_id for o in faction_2_officers})

        for o in faction_2_officers:
            captured = new_state.officer(o.officer_id)
            self.assertEqual(captured.faction_id, "faction_1", "Captured officer must defect to attacking faction")
            self.assertEqual(captured.city_id, "luoyang", "Captured officer must be stationed in captured city")
            self.assertLessEqual(captured.loyalty, 60, "Captured officer loyalty must be <= 60")
            self.assertTrue(captured.is_alive, "Captured officer must remain alive")

        state_after_update = update_faction_status(new_state)
        self.assertFalse(state_after_update.faction("faction_2").is_active, "Eliminated faction must be inactive")

    # -------------------------------------------------------------------------
    # 10. compute_winner
    # -------------------------------------------------------------------------
    def test_compute_winner_more_cities_wins(self):
        # faction_1 has 2 cities with 100 troops each; faction_2 has 1 city with 9999 troops
        cities = dict(self.state.cities)
        cities["xuchang"] = replace(cities["xuchang"], owner="faction_1", troops=100)
        cities["chenliu"] = replace(cities["chenliu"], owner="faction_1", troops=100)
        cities["luoyang"] = replace(cities["luoyang"], owner="faction_2", troops=9999)
        cities["xiangyang"] = replace(cities["xiangyang"], owner="faction_3", troops=50)
        cities["jianye"] = replace(cities["jianye"], owner="faction_3", troops=50)
        custom_state = replace(self.state, cities=cities)

        # faction_1 has 2 cities (200 troops), faction_3 has 2 cities (100 troops), faction_2 has 1 city (9999 troops)
        # Between faction_1 and faction_3: same cities (2), faction_1 has more troops (200 > 100)
        self.assertEqual(compute_winner(custom_state), "faction_1")

    def test_compute_winner_equal_cities_more_troops_wins(self):
        # Each faction owns 1 city: faction_2 has highest troops
        cities = {
            "xuchang": replace(self.state.city("xuchang"), owner="faction_1", troops=1000),
            "luoyang": replace(self.state.city("luoyang"), owner="faction_2", troops=2500),
            "jianye": replace(self.state.city("jianye"), owner="faction_3", troops=800),
        }
        custom_state = replace(self.state, cities=cities)
        self.assertEqual(compute_winner(custom_state), "faction_2")

    def test_compute_winner_exact_tie_returns_none(self):
        # Both faction_1 and faction_2 have 1 city and exactly 1000 troops
        cities = {
            "xuchang": replace(self.state.city("xuchang"), owner="faction_1", troops=1000),
            "luoyang": replace(self.state.city("luoyang"), owner="faction_2", troops=1000),
        }
        custom_state = replace(self.state, cities=cities)
        self.assertIsNone(compute_winner(custom_state))

    # -------------------------------------------------------------------------
    # 11. Early termination
    # -------------------------------------------------------------------------
    def test_game_early_termination_with_single_active_faction(self):
        # When <= 1 active faction remains, Game.run(50) terminates early with turn < 50
        cities = {cid: replace(c, owner="faction_1") for cid, c in self.state.cities.items()}
        state = update_faction_status(replace(self.state, cities=cities))
        active_factions = sum(1 for f in state.factions.values() if f.is_active)
        self.assertEqual(active_factions, 1)

        agents = {fid: RuleBasedAgent() for fid in state.factions}
        game = Game(state, agents, random.Random(42))
        final_state = game.run(50)
        self.assertLess(final_state.turn, 50)
        self.assertEqual(final_state.turn, 0)

    # -------------------------------------------------------------------------
    # 12. Turn order randomization
    # -------------------------------------------------------------------------
    def test_turn_order_randomized_across_seeds(self):
        # Scanning seeds 0-19 must reveal at least 2 distinct first-acting factions in turn 1
        first_acting_factions = set()
        for seed in range(20):
            state = build_initial_state()
            agents = {fid: RuleBasedAgent() for fid in state.factions}
            game = Game(state, agents, random.Random(seed))
            game.step()
            self.assertGreater(len(game.log_entries), 0)
            first_fid = game.log_entries[0].faction_id
            first_acting_factions.add(first_fid)

        self.assertGreaterEqual(
            len(first_acting_factions),
            2,
            f"Expected at least 2 different first-acting factions across seeds 0-19, got {first_acting_factions}",
        )

    # -------------------------------------------------------------------------
    # 13. RuleBasedAgent styles & behavior
    # -------------------------------------------------------------------------
    def test_rule_based_agent_styles_and_invalid_style_error(self):
        # All three styles can be instantiated and return valid decisions
        officer = self.state.officer("xiahou_dun")
        legal = generate_legal_actions(self.state, officer)
        for style in ("balanced", "aggressive", "turtle"):
            agent = RuleBasedAgent(style)
            decision = agent.decide(self.state, officer, legal)
            ok, reason = validate_decision(self.state, officer, decision)
            self.assertTrue(ok, f"Style '{style}' decision invalid: {reason}")

        # Invalid style must raise ValueError
        with self.assertRaises(ValueError):
            RuleBasedAgent("foo")

    def test_rule_based_agent_aggressive_attacks_before_turtle(self):
        # Craft a situation where ratio is between 1.0 (aggressive) and 2.0 (turtle).
        # Target has 1000 troops. Aggressive needs garrison * 0.7 >= 1000 * 1.0 = 1000 (garrison >= 1429).
        # Turtle needs garrison * 0.7 >= 1000 * 2.0 = 2000 (garrison >= 2858).
        # With garrison = 2000: garrison * 0.7 = 1400.
        # 1000 <= 1400 < 2000: aggressive chooses siege, turtle does not choose siege.
        cities = dict(self.state.cities)
        cities["xuchang"] = replace(cities["xuchang"], troops=2000, food=5000)
        cities["luoyang"] = replace(cities["luoyang"], troops=1000)
        state = replace(self.state, cities=cities)

        officer = state.officer("xiahou_dun")
        legal = generate_legal_actions(state, officer)

        agg_decision = RuleBasedAgent("aggressive").decide(state, officer, legal)
        turt_decision = RuleBasedAgent("turtle").decide(state, officer, legal)

        self.assertEqual(agg_decision.action, "siege")
        self.assertEqual(agg_decision.params["to"], "luoyang")
        self.assertNotEqual(turt_decision.action, "siege")

    # -------------------------------------------------------------------------
    # 14. RandomAgent validity & siege params
    # -------------------------------------------------------------------------
    def test_random_agent_validity_and_siege_parameters(self):
        officer_ids = sorted(self.state.officers)
        siege_decisions_seen = 0

        # Sweep 100 decisions across multiple random states and officers
        for i in range(100):
            rng = random.Random(i + 1000)
            agent = RandomAgent(rng)
            # Pick an officer, giving favorable conditions for variety of actions
            oid = officer_ids[i % len(officer_ids)]
            officer = self.state.officer(oid)
            legal = generate_legal_actions(self.state, officer)
            decision = agent.decide(self.state, officer, legal)

            ok, reason = validate_decision(self.state, officer, decision)
            self.assertTrue(ok, f"RandomAgent decision at iteration {i} invalid: {reason}")

            if decision.action == "siege":
                siege_decisions_seen += 1
                self.assertIn("to", decision.params)
                self.assertIn("troops", decision.params)
                self.assertIsInstance(decision.params["troops"], int)

        # In addition, deliberately invoke RandomAgent on a state with legal siege to verify parameters
        xiahou_dun = self.state.officer("xiahou_dun")
        legal_xiahou = generate_legal_actions(self.state, xiahou_dun)
        for seed in range(50):
            agent = RandomAgent(random.Random(seed))
            decision = agent.decide(self.state, xiahou_dun, legal_xiahou)
            ok, reason = validate_decision(self.state, xiahou_dun, decision)
            self.assertTrue(ok, reason)
            if decision.action == "siege":
                siege_decisions_seen += 1
                self.assertIn("to", decision.params)
                self.assertIn("troops", decision.params)

        self.assertGreater(siege_decisions_seen, 0, "Expected at least one siege decision to be tested")


if __name__ == "__main__":
    unittest.main()
