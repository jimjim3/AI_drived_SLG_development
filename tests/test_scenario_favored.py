"""The attack scenario can favor any lord; the legacy id keeps favoring faction_2."""
import unittest

from slg.engine.initial_state import build_initial_state, parse_scenario, resolve_scenario


def _troops(state):
    out = {}
    for c in state.cities.values():
        out[c.owner] = out.get(c.owner, 0) + c.troops
    return out


class TestFavoredScenario(unittest.TestCase):
    def test_legacy_advantage_is_faction_2(self):
        self.assertEqual(parse_scenario("advantage"), ("advantage", "faction_2"))
        a, b = build_initial_state("advantage"), build_initial_state("advantage:faction_2")
        self.assertEqual(a.cities, b.cities)

    def test_each_lord_gets_the_boost_and_only_neighbours_lose(self):
        base = build_initial_state("default")
        for fid in ("faction_1", "faction_2", "faction_3"):
            st = build_initial_state(f"advantage:{fid}")
            for cid, c in st.cities.items():
                b = base.city(cid)
                if c.owner == fid:
                    self.assertEqual(c.troops, int(b.troops * 2.5), cid)
                    self.assertEqual(c.gold, int(b.gold * 1.5), cid)
                    continue
                near = any(base.city(n).owner == fid for n in base.adjacency[cid])
                self.assertEqual(c.troops, int(b.troops * 0.5) if near else b.troops, cid)
                self.assertEqual(c.gold, b.gold, cid)

    def test_favored_lord_is_the_strongest(self):
        for fid in ("faction_1", "faction_2", "faction_3"):
            t = _troops(build_initial_state(f"advantage:{fid}"))
            self.assertEqual(max(t, key=t.get), fid)

    def test_resolve_scenario(self):
        self.assertEqual(resolve_scenario("default", "faction_1"), "default")
        self.assertEqual(resolve_scenario("advantage", "faction_3"), "advantage:faction_3")
        with self.assertRaises(ValueError):
            resolve_scenario("advantage", "faction_9")

    def test_unknown_scenarios_rejected(self):
        for bad in ("nope", "advantage:faction_9", "default:faction_1"):
            with self.assertRaises(ValueError):
                build_initial_state(bad)


if __name__ == "__main__":
    unittest.main()
