import unittest
from dataclasses import replace

from slg.engine.initial_state import build_initial_state
from slg.engine.validation import validate_decision
from slg.schema import AgentDecision


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()

    def test_develop_valid(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "develop_agri", {}),
        )
        self.assertTrue(ok, reason)

    def test_recruit_valid(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "recruit", {"troops": 100}),
        )
        self.assertTrue(ok, reason)

    def test_recruit_out_of_range(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "recruit", {"troops": 999999}),
        )
        self.assertFalse(ok)

    def test_recruit_off_step(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "recruit", {"troops": 150}),
        )
        self.assertFalse(ok)

    def test_unknown_action(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "teleport", {}),
        )
        self.assertFalse(ok)

    def test_officer_id_mismatch(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("guan_yu", "develop_agri", {}),
        )
        self.assertFalse(ok)

    def test_move_valid(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "move", {"to": "chenliu"}),
        )
        self.assertTrue(ok, reason)

    def test_move_invalid_target(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xun_yu"),
            AgentDecision("xun_yu", "move", {"to": "luoyang"}),
        )
        self.assertFalse(ok)

    def test_move_non_adjacent_friendly_city_rejected(self):
        # xiangyang is faction_1's but not adjacent to chenliu
        ok, reason = validate_decision(
            self.state,
            self.state.officer("cao_ren"),
            AgentDecision("cao_ren", "move", {"to": "xiangyang"}),
        )
        self.assertFalse(ok)
        self.assertIn("choices", reason)

    def test_siege_valid(self):
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xiahou_dun"),
            AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 500}),
        )
        self.assertTrue(ok, reason)

    def test_siege_non_adjacent_city_rejected(self):
        # jianye is an enemy city but not adjacent to xuchang
        ok, reason = validate_decision(
            self.state,
            self.state.officer("xiahou_dun"),
            AgentDecision("xiahou_dun", "siege", {"to": "jianye", "troops": 500}),
        )
        self.assertFalse(ok)

    def test_develop_insufficient_gold(self):
        city = self.state.city("xuchang")
        state = replace(
            self.state,
            cities={**self.state.cities, "xuchang": replace(city, gold=49)},
        )
        ok, reason = validate_decision(
            state,
            state.officer("xun_yu"),
            AgentDecision("xun_yu", "develop_agri", {}),
        )
        self.assertFalse(ok)

    def test_dead_officer_invalid(self):
        officer = self.state.officer("xun_yu")
        state = replace(
            self.state,
            officers={
                **self.state.officers,
                "xun_yu": replace(officer, is_alive=False),
            },
        )
        ok, reason = validate_decision(
            state,
            state.officer("xun_yu"),
            AgentDecision("xun_yu", "rest", {}),
        )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
