import unittest

from slg.sim.headless import run_headless


class FullGameTests(unittest.TestCase):
    def test_20_turn_game_completes(self):
        result = run_headless(seed=42, turns=20)
        final = result.final_state
        # The game runs 20 turns unless it ends early with <= 1 active faction.
        self.assertLessEqual(final.turn, 20)
        active = [f for f in final.factions.values() if f.is_active]
        if final.turn < 20:
            self.assertLessEqual(len(active), 1)
        else:
            self.assertGreater(len(active), 1)
        self.assertEqual(len(final.cities), 9)
        self.assertEqual(len(final.officers), 42)
        self.assertEqual(result.stats["valid"], result.stats["decisions"])
        self.assertEqual(len(result.events), result.stats["decisions"])

        if result.winner is not None:
            # Winner is the unique lexicographic max of (cities, total troops).
            def score(fid):
                owned = [c for c in final.cities.values() if c.owner == fid]
                return (len(owned), sum(c.troops for c in owned))

            winner_score = score(result.winner)
            for fid in final.factions:
                if fid == result.winner:
                    continue
                self.assertGreater(winner_score, score(fid))

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
