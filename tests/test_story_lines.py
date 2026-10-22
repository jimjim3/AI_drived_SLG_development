import unittest
from dataclasses import replace

from slg.engine.initial_state import build_initial_state
from slg.schema import ResolutionEvent
from slg.web.payload import story_lines


def _siege(state, faction, officer, city, captured, defender):
    return ResolutionEvent(1, officer, faction, "siege", city, "x",
                           captured_city=city if captured else None, defender_faction=defender)


class StoryLinesTests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()

    def test_own_victory_and_defeat_are_told_from_the_players_side(self):
        ev = [_siege(self.state, "faction_1", "xiahou_dun", "luoyang", True, "faction_2")]
        mine = story_lines(ev, self.state, "faction_1")
        theirs = story_lines(ev, self.state, "faction_2")
        self.assertEqual(len(mine), 1)
        self.assertIn("夏侯惇", mine[0])
        self.assertIn("洛陽", mine[0])
        self.assertEqual(len(theirs), 1)
        self.assertIn("洛陽", theirs[0])
        self.assertNotIn("夏侯惇", theirs[0])  # the loser's text names the city, not the enemy officer

    def test_repelled_attack_reads_as_defence_for_the_defender(self):
        ev = [_siege(self.state, "faction_1", "xiahou_dun", "luoyang", False, "faction_2")]
        self.assertEqual(len(story_lines(ev, self.state, "faction_1")), 1)
        self.assertEqual(len(story_lines(ev, self.state, "faction_2")), 1)

    def test_other_factions_fight_is_not_told(self):
        ev = [_siege(self.state, "faction_1", "xiahou_dun", "luoyang", True, "faction_2")]
        # faction_3 sees luoyang as neither its own nor on its frontier here
        self.assertEqual(story_lines(ev, self.state, "faction_3"), [])

    def test_routine_actions_are_not_narrated(self):
        ev = [ResolutionEvent(1, "xiahou_dun", "faction_1", "develop_agri", "xuchang", "ok")]
        self.assertEqual(story_lines(ev, self.state, "faction_1"), [])


if __name__ == "__main__":
    unittest.main()
