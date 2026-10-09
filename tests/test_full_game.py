import unittest

from slg.sim.headless import run_headless


class FullGameTests(unittest.TestCase):
    def test_20_turn_game_completes(self):
        result = run_headless(seed=42, turns=20)
        self.assertEqual(result.final_state.turn, 20)
        self.assertEqual(len(result.final_state.cities), 5)
        self.assertEqual(len(result.final_state.officers), 20)
        self.assertEqual(result.stats["valid"], result.stats["decisions"])
        self.assertEqual(len(result.events), result.stats["decisions"])

        if result.winner is not None:
            winner_cities = sum(
                1
                for city in result.final_state.cities.values()
                if city.owner == result.winner
            )
            self.assertGreaterEqual(winner_cities, 3)
            self.assertGreaterEqual(winner_cities, 5 - winner_cities)

        for officer in result.final_state.officers.values():
            self.assertIn(officer.faction_id, ("faction_1", "faction_2", "faction_3"))
            self.assertIn(officer.city_id, result.final_state.cities)

    def test_all_events_use_known_actions(self):
        result = run_headless(seed=42, turns=20)
        known = {
            "develop_agri",
            "develop_commerce",
            "develop_defense",
            "recruit",
            "move",
            "siege",
            "rest",
        }
        for event in result.events:
            self.assertIn(event.action, known)


if __name__ == "__main__":
    unittest.main()
