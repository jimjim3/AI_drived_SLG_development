import unittest

from slg import narrative
from slg.web.payload import scene_text


class TransitionTests(unittest.TestCase):
    def test_every_pool_has_four_nonempty_texts(self):
        t = narrative.load_narrative()["transitions"]
        for key, pool in t.items():
            groups = pool.values() if isinstance(pool, dict) else [pool]
            for g in groups:
                self.assertEqual(len(g), 4, key)
                self.assertTrue(all(x.strip() for x in g), key)

    def test_transition_is_deterministic_and_wraps(self):
        self.assertEqual(narrative.transition("quiet_turn", 1), narrative.transition("quiet_turn", 5))
        self.assertTrue(narrative.transition("season_change", 3, season="夏"))

    def test_scene_text_by_turn(self):
        self.assertEqual(scene_text(1, False), {})
        t2 = scene_text(2, False)  # turn 2 opens summer of year 1
        self.assertIn("quiet", t2)
        self.assertNotIn("new_year", t2)
        t5 = scene_text(5, True)  # turn 5 opens spring of year 2
        self.assertIn("new_year", t5)
        self.assertNotIn("quiet", t5)


if __name__ == "__main__":
    unittest.main()
