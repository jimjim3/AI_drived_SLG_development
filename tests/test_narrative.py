"""Story text must stay consistent with the engine's scenario data."""
import re
import unittest

from slg import narrative
from slg.engine.initial_state import build_initial_state, resolve_scenario

SCENARIOS = ("default", "advantage")
LATIN = re.compile(r"[A-Za-z]")
DEATH = re.compile(r"託孤|先帝|殉漢|殉國|駕崩|崩殂|已逝|逝世|遺志|遺命|遺詔|陣亡|病逝|病卒|身亡|戰死|被殺|遇害|早逝|歿|薨|自盡|飲鴆|伏誅|身死")
BOILERPLATE = re.compile(r"非謂實錄|史官之記|史官之筆|史官之論|史官之嘆|假想世|此乃")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _han(s):
    return len(re.findall(r"[一-鿿]", s))


def _expected_tone(state, faction_id):
    """Same rule the texts were written against: derived from engine troop totals."""
    tot = {f: sum(c.troops for c in state.cities.values() if c.owner == f) for f in state.factions}
    mine = tot[faction_id]
    front = [c for c in state.cities.values() if c.owner == faction_id
             and any(state.city(n).owner != faction_id for n in state.adjacency[c.city_id])]
    foes = {state.city(n).owner for c in front for n in state.adjacency[c.city_id] if state.city(n).owner != faction_id}
    ratios = [mine / tot[e] for e in foes]
    if any(r >= 1.8 for r in ratios) and min(ratios) >= 1.8:
        return "優勢"
    weakest = sorted(tot, key=lambda k: -tot[k]).index(faction_id) == 2
    if weakest or any(r < 0.55 for r in ratios):
        return "劣勢"
    return "均勢"


class TestNarrativeCoverage(unittest.TestCase):
    def setUp(self):
        self.n = narrative.load_narrative()

    def test_every_officer_city_and_lord_has_text(self):
        state = build_initial_state("default")
        self.assertEqual(set(self.n["officers"]), set(state.officers))
        self.assertEqual(set(self.n["world"]["cities"]), set(state.cities))
        self.assertEqual(set(self.n["world"]["lords"]), set(state.factions))
        for fid, f in state.factions.items():
            self.assertEqual(self.n["world"]["lords"][fid]["name"], f.name)

    def test_officer_names_match_engine(self):
        state = build_initial_state("default")
        for oid, o in state.officers.items():
            self.assertEqual(self.n["officers"][oid]["name"], o.name, oid)

    def test_one_opening_per_scenario_and_lord(self):
        expected = {f"{s}.{f}" for s in SCENARIOS for f in build_initial_state("default").factions}
        self.assertEqual(set(self.n["openings"]), expected)

    def test_events_have_declared_placeholders_only(self):
        allowed = {"officer", "city", "target", "faction", "lord", "troops"}
        names = [o["name"] for o in self.n["officers"].values()] + [c["name"] for c in self.n["world"]["cities"].values()]
        for key, variants in self.n["events"].items():
            self.assertEqual(len(variants), 4, key)
            for t in variants:
                self.assertLessEqual(set(re.findall(r"\{(\w+)\}", t)), allowed, t)
                core = re.sub(r"\{\w+\}", "", t)
                for nm in names:
                    self.assertNotIn(nm, core, f"{key} hard-codes {nm}")

    def test_render_event_fills_and_wraps_variants(self):
        a = narrative.render_event("recruit", 0, officer="張遼", city="許昌", troops=600)
        self.assertIn("張遼", a)
        self.assertNotIn("{", a)
        self.assertEqual(narrative.render_event("recruit", 4, officer="張遼", city="許昌", troops=600), a)
        with self.assertRaises(KeyError):
            narrative.render_event("recruit", 0, officer="張遼")


class TestOpeningsMatchEngine(unittest.TestCase):
    def test_opening_matches_lord_cities_roster_and_strength(self):
        n = narrative.load_narrative()
        for sc in SCENARIOS:
            for fid in build_initial_state("default").factions:
                state = build_initial_state(resolve_scenario(sc, fid))  # attack scenario favors the chosen lord
                op = narrative.opening(sc, fid)
                text = op["headline"] + op["situation"] + "".join(op["advice"])
                own = [c.name for c in state.cities.values() if c.owner == fid]
                for name in own:
                    self.assertIn(name, op["situation"], f"{sc}.{fid} omits own city {name}")
                roster = {o.name for o in state.officers.values() if o.faction_id == fid}
                others = {o.name for o in state.officers.values() if o.faction_id != fid}
                for name in others:
                    self.assertNotIn(name, text, f"{sc}.{fid} mentions foreign officer {name}")
                self.assertEqual(op["tone"], _expected_tone(state, fid), f"{sc}.{fid}")
                self.assertEqual(len(op["advice"]), 3)
                self.assertTrue(roster)  # sanity

    def test_scenarios_give_different_openings_for_the_same_lord(self):
        for fid in ("faction_1", "faction_2", "faction_3"):
            self.assertNotEqual(narrative.opening("default", fid)["situation"],
                                narrative.opening("advantage", fid)["situation"])
        for fid in ("faction_1", "faction_2", "faction_3"):
            self.assertEqual(narrative.opening("advantage", fid)["tone"], "優勢", fid)
        self.assertEqual(narrative.opening("advantage:faction_1", "faction_1"), narrative.opening("advantage", "faction_1"))


class TestHygiene(unittest.TestCase):
    def test_no_latin_death_or_boilerplate(self):
        n = narrative.load_narrative()
        for s in _strings({k: n[k] for k in ("world", "officers", "events", "openings")}):
            self.assertIsNone(LATIN.search(re.sub(r"\{\w+\}", "", s)), s)
            self.assertIsNone(BOILERPLATE.search(s), s)
        # officers are alive and in service: no endings in their bios/quotes
        for oid, o in n["officers"].items():
            for k in ("bio", "quote", "tag", "tie"):
                self.assertIsNone(DEATH.search(o[k]), f"{oid}.{k}: {o[k]}")

    def test_officer_text_lengths(self):
        for oid, o in narrative.load_narrative()["officers"].items():
            self.assertTrue(60 <= _han(o["bio"]) <= 105, (oid, _han(o["bio"])))
            self.assertTrue(8 <= _han(o["quote"]) <= 24, oid)
            self.assertTrue(4 <= _han(o["tag"]) <= 14, oid)
            self.assertTrue(o["title"] and o["tie"], oid)


class TestCalendar(unittest.TestCase):
    def test_four_seasons_per_year(self):
        labels = [narrative.calendar_label(t)["label"] for t in range(5)]
        self.assertEqual(labels, ["第1年春", "第1年夏", "第1年秋", "第1年冬", "第2年春"])
        with self.assertRaises(ValueError):
            narrative.calendar_label(-1)


if __name__ == "__main__":
    unittest.main()
