"""Unit tests for Scenario v3 and Task E requirements.

Verifies:
1. City count >= 8 and total officer count >= 40.
2. Adjacency graph is bidirectional and fully connected (via BFS traversal).
3. Preserves all legacy adjacency edges.
4. Each faction owns >= 2 cities.
5. Each faction has >= 12 officers.
6. Officers of each faction are distributed across >= 2 cities.
7. Officer IDs are globally unique.
8. All officer stats (politics, war, leadership, loyalty, ambition) are in [0, 100].
9. Preserves all 20 legacy officers with their original stats.
10. CAST_LIMIT is strictly less than each faction's officer count, and select_cast
    produces cast length == CAST_LIMIT while leaving roster non-empty.
11. Siege victory relocates the attacking officer to the target city.
12. Siege defeat (repelled) leaves the attacking officer at the origin city.
"""

from collections import deque
from dataclasses import replace
import random
import unittest

from slg.engine.initial_state import build_initial_state
from slg.engine.resolution import resolve_decision
from slg.engine.view import build_faction_view, select_cast
from slg.schema import AgentDecision, CAST_LIMIT


class ScenarioV3Tests(unittest.TestCase):
    def setUp(self):
        self.state = build_initial_state()
        self.rng = random.Random(42)

    def test_city_count_lower_bound(self):
        """Scenario must contain at least 8 cities."""
        self.assertGreaterEqual(len(self.state.cities), 8)

    def test_officer_count_lower_bound(self):
        """Scenario must contain at least 40 officers."""
        self.assertGreaterEqual(len(self.state.officers), 40)

    def test_adjacency_bidirectional(self):
        """Every edge in the adjacency map must be bidirectional."""
        for city_id, neighbors in self.state.adjacency.items():
            self.assertIn(city_id, self.state.cities, f"Adjacency key '{city_id}' not in cities")
            for neighbor in neighbors:
                self.assertIn(neighbor, self.state.cities, f"Neighbor '{neighbor}' not in cities")
                self.assertIn(
                    city_id,
                    self.state.adjacency.get(neighbor, ()),
                    f"Adjacency {city_id} -> {neighbor} is not bidirectional",
                )

    def test_adjacency_graph_connected(self):
        """The city adjacency graph must be fully connected via BFS graph traversal."""
        start_city = next(iter(self.state.cities))
        visited = set()
        queue = deque([start_city])

        while queue:
            curr = queue.popleft()
            if curr in visited:
                continue
            visited.add(curr)
            for nbr in self.state.adjacency.get(curr, ()):
                if nbr not in visited:
                    queue.append(nbr)

        self.assertEqual(
            visited,
            set(self.state.cities.keys()),
            "Graph traversal did not reach all cities; map is disconnected",
        )

    def test_legacy_edges_preserved(self):
        """Preserves legacy edges: chenliu-xuchang, xuchang-luoyang, xuchang-xiangyang,
        xiangyang-luoyang, xiangyang-jianye.
        """
        legacy_edges = [
            ("chenliu", "xuchang"),
            ("xuchang", "luoyang"),
            ("xuchang", "xiangyang"),
            ("xiangyang", "luoyang"),
            ("xiangyang", "jianye"),
        ]
        for u, v in legacy_edges:
            self.assertIn(v, self.state.adjacency.get(u, ()), f"Missing edge {u} -> {v}")
            self.assertIn(u, self.state.adjacency.get(v, ()), f"Missing edge {v} -> {u}")

    def test_each_faction_has_at_least_two_cities(self):
        """Every active faction must control at least 2 cities."""
        for fid in self.state.factions:
            owned = [c for c in self.state.cities.values() if c.owner == fid]
            self.assertGreaterEqual(
                len(owned),
                2,
                f"Faction {fid} controls {len(owned)} cities, expected >= 2",
            )

    def test_each_faction_has_at_least_twelve_officers(self):
        """Every faction must have at least 12 officers."""
        for fid in self.state.factions:
            officers = self.state.officers_of(fid)
            self.assertGreaterEqual(
                len(officers),
                12,
                f"Faction {fid} has {len(officers)} officers, expected >= 12",
            )

    def test_each_faction_officers_distributed_across_at_least_two_cities(self):
        """Officers of each faction must be distributed across at least 2 distinct cities."""
        for fid in self.state.factions:
            cities_with_officers = {
                o.city_id for o in self.state.officers_of(fid)
            }
            self.assertGreaterEqual(
                len(cities_with_officers),
                2,
                f"Faction {fid} officers reside in {cities_with_officers}, expected >= 2 cities",
            )

    def test_officer_ids_unique(self):
        """All officer IDs must be globally unique."""
        all_ids = [o.officer_id for o in self.state.officers.values()]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_officer_stats_range_0_to_100(self):
        """Every officer stat must be within [0, 100]."""
        for o in self.state.officers.values():
            for stat_name in ("politics", "war", "leadership", "loyalty", "ambition"):
                val = getattr(o, stat_name)
                self.assertGreaterEqual(val, 0, f"{o.officer_id} {stat_name}={val} < 0")
                self.assertLessEqual(val, 100, f"{o.officer_id} {stat_name}={val} > 100")

    def test_legacy_twenty_officers_preserved_with_exact_stats(self):
        """The 20 legacy officers must exist with identical stats."""
        legacy_stats = {
            "xun_yu": (95, 30, 60, 90, 30),
            "xiahou_dun": (40, 85, 85, 85, 40),
            "yu_jin": (45, 78, 78, 80, 45),
            "dian_wei": (20, 90, 75, 80, 50),
            "cao_ren": (50, 80, 80, 88, 35),
            "li_dian": (60, 70, 70, 82, 30),
            "yue_jin": (55, 80, 72, 80, 50),
            "cheng_yu": (60, 75, 68, 80, 50),
            "zhuge_liang": (98, 60, 75, 95, 20),
            "guan_yu": (65, 95, 90, 92, 30),
            "zhang_fei": (30, 92, 85, 90, 40),
            "zhao_yun": (50, 93, 88, 93, 25),
            "huang_zhong": (40, 88, 82, 85, 35),
            "wei_yan": (40, 85, 78, 85, 45),
            "zhou_yu": (85, 75, 90, 80, 50),
            "lu_su": (80, 40, 60, 80, 50),
            "taishi_ci": (45, 85, 78, 80, 50),
            "huang_gai": (50, 78, 70, 80, 50),
            "gan_ning": (30, 92, 80, 80, 50),
            "zhou_tai": (40, 80, 75, 80, 50),
        }
        for oid, expected in legacy_stats.items():
            o = self.state.officer(oid)
            actual = (o.politics, o.war, o.leadership, o.loyalty, o.ambition)
            self.assertEqual(actual, expected, f"Officer {oid} stats mismatch: {actual} vs {expected}")

    def test_cast_limit_smaller_than_faction_officers_and_roster_non_empty(self):
        """CAST_LIMIT < faction officer count, and select_cast yields len == CAST_LIMIT with non-empty roster."""
        for fid in self.state.factions:
            faction_officers = self.state.officers_of(fid)
            self.assertGreater(
                len(faction_officers),
                CAST_LIMIT,
                f"Faction {fid} has {len(faction_officers)} officers, which does not exceed CAST_LIMIT ({CAST_LIMIT})",
            )
            cast = select_cast(self.state, fid, limit=CAST_LIMIT)
            self.assertEqual(len(cast), CAST_LIMIT)
            view = build_faction_view(self.state, fid, cast_ids=cast)
            self.assertEqual(len(view.cast), CAST_LIMIT)
            total_roster_officers = sum(len(names) for names in view.roster.values())
            self.assertEqual(total_roster_officers, len(faction_officers) - CAST_LIMIT)
            self.assertGreater(total_roster_officers, 0)

    def test_siege_victory_moves_attacking_officer_to_target_city(self):
        """On siege victory (atk > dfn), the attacking officer is relocated to target city."""
        xuchang = replace(self.state.city("xuchang"), troops=5000)
        luoyang = replace(self.state.city("luoyang"), troops=100, defense=0)
        state = replace(
            self.state,
            cities={**self.state.cities, "xuchang": xuchang, "luoyang": luoyang},
        )
        officer = state.officer("xiahou_dun")
        self.assertEqual(officer.city_id, "xuchang")

        new_state, event = resolve_decision(
            state,
            officer,
            AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 4000}),
            self.rng,
        )
        self.assertEqual(event.captured_city, "luoyang")
        self.assertEqual(
            new_state.officer("xiahou_dun").city_id,
            "luoyang",
            "Attacking officer must relocate to captured city upon victory",
        )

    def test_siege_defeat_leaves_attacking_officer_at_origin_city(self):
        """On siege defeat (atk <= dfn), the attacking officer remains at origin city."""
        xuchang = replace(self.state.city("xuchang"), troops=1000)
        luoyang = replace(self.state.city("luoyang"), troops=5000, defense=200)
        state = replace(
            self.state,
            cities={**self.state.cities, "xuchang": xuchang, "luoyang": luoyang},
        )
        officer = state.officer("xiahou_dun")
        self.assertEqual(officer.city_id, "xuchang")

        new_state, event = resolve_decision(
            state,
            officer,
            AgentDecision("xiahou_dun", "siege", {"to": "luoyang", "troops": 900}),
            self.rng,
        )
        self.assertIsNone(event.captured_city)
        self.assertEqual(
            new_state.officer("xiahou_dun").city_id,
            "xuchang",
            "Attacking officer must stay at origin city upon defeat",
        )


if __name__ == "__main__":
    unittest.main()
