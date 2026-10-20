import unittest

from slg.engine.initial_state import build_initial_state


class MapVariantTests(unittest.TestCase):
    def test_swap13_trades_cities_and_officers(self):
        base = build_initial_state("default")
        sw = build_initial_state("default+swap13")
        flip = {"faction_1": "faction_3", "faction_3": "faction_1", "faction_2": "faction_2"}
        for cid, c in base.cities.items():
            self.assertEqual(sw.cities[cid].owner, flip[c.owner])
            self.assertEqual(sw.cities[cid].troops, c.troops)
        for oid, o in base.officers.items():
            self.assertEqual(sw.officers[oid].faction_id, flip[o.faction_id])

    def test_sun2_adds_edge_both_ways(self):
        a = build_initial_state("default+sun2").adjacency
        self.assertIn("xiangyang", a["wujun"])
        self.assertIn("wujun", a["xiangyang"])

    def test_default_unchanged(self):
        self.assertNotIn("xiangyang", build_initial_state("default").adjacency["wujun"])


if __name__ == "__main__":
    unittest.main()
