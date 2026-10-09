import random
import unittest
from dataclasses import replace

from slg.engine.initial_state import build_initial_state
from slg.engine.resolution import resolve_decision
from slg.schema import AgentDecision


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()
        self.rng = random.Random(1)

    def _resolve(self, officer_id, action, params, state=None):
        state = state or self.state
        officer = state.officer(officer_id)
        return resolve_decision(
            state,
            officer,
            AgentDecision(officer_id, action, params),
            self.rng,
        )

    def test_develop_agri(self):
        new_state, event = self._resolve("xun_yu", "develop_agri", {})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 950)
        self.assertEqual(city.agriculture, 550)
        self.assertEqual(event.action, "develop_agri")
        self.assertEqual(event.city_id, "xuchang")

    def test_develop_commerce(self):
        new_state, event = self._resolve("xun_yu", "develop_commerce", {})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 950)
        self.assertEqual(city.commerce, 550)
        self.assertEqual(event.action, "develop_commerce")

    def test_develop_defense(self):
        new_state, event = self._resolve("xun_yu", "develop_defense", {})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 950)
        self.assertEqual(city.defense, 175)
        self.assertEqual(event.action, "develop_defense")

    def test_recruit(self):
        new_state, event = self._resolve("xun_yu", "recruit", {"troops": 200})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 800)
        self.assertEqual(city.troops, 1200)
        self.assertEqual(event.action, "recruit")

    def test_move(self):
        new_state, event = self._resolve("xun_yu", "move", {"to": "chenliu"})
        self.assertEqual(new_state.officer("xun_yu").city_id, "chenliu")
        self.assertEqual(new_state.city("xuchang").troops, 1000)
        self.assertEqual(new_state.city("chenliu").troops, 500)
        self.assertEqual(event.action, "move")

    def test_rest(self):
        new_state, event = self._resolve("xun_yu", "rest", {})
        self.assertEqual(new_state, self.state)
        self.assertEqual(event.action, "rest")

    def test_siege_capture(self):
        xuchang = replace(self.state.city("xuchang"), troops=5000)
        luoyang = replace(self.state.city("luoyang"), troops=100, defense=0)
        state = replace(
            self.state,
            cities={
                **self.state.cities,
                "xuchang": xuchang,
                "luoyang": luoyang,
            },
        )
        new_state, event = self._resolve(
            "xiahou_dun",
            "siege",
            {"to": "luoyang"},
            state=state,
        )
        self.assertEqual(new_state.city("luoyang").owner, "faction_1")
        self.assertEqual(new_state.city("luoyang").troops, 0)
        self.assertEqual(new_state.city("xuchang").troops, 0)
        self.assertEqual(event.captured_city, "luoyang")
        self.assertFalse(new_state.officer("guan_yu").is_alive)
        self.assertIn("guan_yu", event.captured_officers)

    def test_siege_repel(self):
        xuchang = replace(self.state.city("xuchang"), troops=1000)
        luoyang = replace(self.state.city("luoyang"), troops=5000, defense=200)
        state = replace(
            self.state,
            cities={
                **self.state.cities,
                "xuchang": xuchang,
                "luoyang": luoyang,
            },
        )
        new_state, event = self._resolve(
            "xiahou_dun",
            "siege",
            {"to": "luoyang"},
            state=state,
        )
        self.assertEqual(new_state.city("luoyang").owner, "faction_2")
        self.assertEqual(new_state.city("xuchang").troops, 700)
        self.assertEqual(new_state.city("luoyang").troops, 3500)
        self.assertEqual(new_state.officer("xiahou_dun").city_id, "xuchang")
        self.assertIsNone(event.captured_city)


if __name__ == "__main__":
    unittest.main()
