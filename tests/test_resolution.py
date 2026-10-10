import unittest
from dataclasses import replace

from slg.engine.initial_state import build_initial_state
from slg.engine.resolution import resolve_decision
from slg.schema import AgentDecision


class FixedUniformRng:
    """RNG stub: uniform() always returns a fixed value so combat formulas
    can be verified by hand computation."""

    def __init__(self, value: float):
        self.value = value

    def uniform(self, a, b):
        return self.value


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()
        # uniform() == 1.0 makes every combat roll exactly its midpoint.
        self.rng = FixedUniformRng(1.0)

    def _resolve(self, officer_id, action, params, state=None, rng=None):
        state = state or self.state
        officer = state.officer(officer_id)
        return resolve_decision(
            state,
            officer,
            AgentDecision(officer_id, action, params),
            rng or self.rng,
        )

    def test_develop_agri(self):
        # xun_yu politics 95: gain = 50 * (50 + 95) // 100 = 72
        new_state, event = self._resolve("xun_yu", "develop_agri", {})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 950)
        self.assertEqual(city.agriculture, 622)
        self.assertEqual(event.action, "develop_agri")
        self.assertEqual(event.city_id, "xuchang")
        self.assertIn("+72", event.detail)

    def test_develop_commerce(self):
        new_state, event = self._resolve("xun_yu", "develop_commerce", {})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 950)
        self.assertEqual(city.commerce, 622)
        self.assertEqual(event.action, "develop_commerce")

    def test_develop_defense(self):
        # defense base 25: gain = 25 * 145 // 100 = 36
        new_state, event = self._resolve("xun_yu", "develop_defense", {})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 950)
        self.assertEqual(city.defense, 186)
        self.assertEqual(event.action, "develop_defense")

    def test_recruit(self):
        new_state, event = self._resolve("xun_yu", "recruit", {"troops": 200})
        city = new_state.city("xuchang")
        self.assertEqual(city.gold, 800)
        self.assertEqual(city.troops, 1600)
        self.assertEqual(event.action, "recruit")

    def test_move(self):
        new_state, event = self._resolve("xun_yu", "move", {"to": "chenliu"})
        self.assertEqual(new_state.officer("xun_yu").city_id, "chenliu")
        self.assertEqual(new_state.city("xuchang").troops, 1400)
        self.assertEqual(new_state.city("chenliu").troops, 800)
        self.assertEqual(event.action, "move")

    def test_rest(self):
        new_state, event = self._resolve("xun_yu", "rest", {})
        self.assertEqual(new_state, self.state)
        self.assertEqual(event.action, "rest")

    def test_siege_capture(self):
        # c = 4000, xiahou_dun (war 85, leadership 85): atk = 4000 * 1.35 = 5400
        # luoyang: 100 troops, defense 0, dq = guan_yu (95+90)/2 = 92.5
        # dfn = 100 * 1.0 * 1.425 = 142.5  ->  atk > dfn, victory
        # loss = int(4000 * min(0.5, max(0.1, 0.4*142.5/5400))) = int(4000*0.1) = 400
        xuchang = replace(self.state.city("xuchang"), troops=5000)
        luoyang = replace(self.state.city("luoyang"), troops=100, defense=0)
        state = replace(
            self.state,
            cities={
                **self.state.cities,
                "xuchang": xuchang,
                "luoyang": luoyang,
                "wancheng": replace(self.state.city("wancheng"), owner="faction_1"),
                "hanzhong": replace(self.state.city("hanzhong"), owner="faction_1"),
            },
        )
        new_state, event = self._resolve(
            "xiahou_dun",
            "siege",
            {"to": "luoyang", "troops": 4000},
            state=state,
        )
        self.assertEqual(new_state.city("luoyang").owner, "faction_1")
        self.assertEqual(new_state.city("luoyang").troops, 3600)
        self.assertEqual(new_state.city("xuchang").troops, 1000)
        self.assertEqual(event.captured_city, "luoyang")
        self.assertEqual(new_state.officer("xiahou_dun").city_id, "luoyang")
        # faction_2 lost its last city: its officers defect to faction_1
        self.assertIn("guan_yu", event.captured_officers)
        self.assertEqual(len(event.captured_officers), 3)
        guan_yu = new_state.officer("guan_yu")
        self.assertTrue(guan_yu.is_alive)
        self.assertEqual(guan_yu.faction_id, "faction_1")
        self.assertEqual(guan_yu.city_id, "luoyang")
        self.assertEqual(guan_yu.loyalty, 60)

    def test_siege_repel(self):
        # c = 900 (max, keeps 100 garrison): atk = 900 * 1.35 = 1215
        # luoyang: 5000 troops, defense 200, dq 92.5:
        # dfn = 5000 * 2.0 * 1.425 = 14250  ->  atk <= dfn, repelled
        # attacker loss = int(900 * min(0.8, max(0.3, 0.5*14250/1215))) = 720
        # defender loss = int(5000 * min(0.3, 0.15*1215/14250)) = int(63.95) = 63
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
            {"to": "luoyang", "troops": 900},
            state=state,
        )
        self.assertEqual(new_state.city("luoyang").owner, "faction_2")
        self.assertEqual(new_state.city("xuchang").troops, 280)
        self.assertEqual(new_state.city("luoyang").troops, 4937)
        self.assertEqual(new_state.officer("xiahou_dun").city_id, "xuchang")
        self.assertIsNone(event.captured_city)


if __name__ == "__main__":
    unittest.main()
