import json
import unittest

from slg.engine.initial_state import build_initial_state
from slg.engine.legal_actions import generate_legal_actions
from slg.engine.view import (
    build_faction_view,
    describe_events,
    forced_cast,
    format_legal,
    select_cast,
)
from slg.schema import (
    CAST_LIMIT,
    EVENT_LIMIT,
    LegalAction,
    ParamSpec,
    ResolutionEvent,
)


class ViewTests(unittest.TestCase):
    def test_format_legal_no_params(self):
        la = LegalAction("develop_agri")
        self.assertEqual(format_legal(la), "develop_agri")

    def test_format_legal_numeric_param(self):
        la = LegalAction(
            "recruit",
            params={"troops": ParamSpec("troops", min=100, max=1200, step=100)},
        )
        self.assertEqual(format_legal(la), "recruit troops=100..1200/100")

    def test_format_legal_discrete_param(self):
        la = LegalAction(
            "move",
            params={"to": ParamSpec("to", choices=("chenliu", "xiangyang"))},
        )
        self.assertEqual(format_legal(la), "move to=[chenliu,xiangyang]")

    def test_format_legal_multi_params(self):
        la = LegalAction(
            "siege",
            params={
                "to": ParamSpec("to", choices=("luoyang",)),
                "troops": ParamSpec("troops", min=500, max=1100, step=100),
            },
        )
        self.assertEqual(format_legal(la), "siege to=[luoyang] troops=500..1100/100")

    def test_select_cast_order_forced_before_requested(self):
        state = build_initial_state()
        # xun_yu (politics 95, war 30, lead 60 = 185)
        # xiahou_dun (40, 85, 85 = 210)
        # We request xiahou_dun (higher stats) and force xun_yu (lower stats).
        # Forced MUST come before requested regardless of stats.
        cast = select_cast(
            state,
            "faction_1",
            requested=("xiahou_dun",),
            forced=("xun_yu",),
            limit=2,
        )
        self.assertEqual(cast, ("xun_yu", "xiahou_dun"))

    def test_select_cast_dedup(self):
        state = build_initial_state()
        cast = select_cast(
            state,
            "faction_1",
            requested=("xun_yu", "xiahou_dun", "xiahou_dun"),
            forced=("xun_yu", "xun_yu"),
            limit=CAST_LIMIT,
        )
        # xun_yu was forced, so it is first; xiahou_dun was requested; each appears once.
        self.assertEqual(cast[:2], ("xun_yu", "xiahou_dun"))
        self.assertEqual(len(cast), len(set(cast)))

    def test_select_cast_filters_other_faction_and_dead(self):
        state = build_initial_state()
        # zhuge_liang belongs to faction_2
        # Dian Wei is faction_1; let's create a state where dian_wei is dead
        officers = dict(state.officers)
        officers["dian_wei"] = officers["dian_wei"].__class__(
            **{**officers["dian_wei"].__dict__, "is_alive": False}
        )
        state_with_dead = state.__class__(**{**state.__dict__, "officers": officers})

        cast = select_cast(
            state_with_dead,
            "faction_1",
            requested=("zhuge_liang", "dian_wei", "xun_yu"),
            forced=("zhuge_liang",),
            limit=1,
        )
        self.assertEqual(cast, ("xun_yu",))

    def test_select_cast_limit_truncation(self):
        state = build_initial_state()
        # 4 requested officers, limit=2
        cast = select_cast(
            state,
            "faction_1",
            requested=("xun_yu", "xiahou_dun", "yu_jin", "dian_wei"),
            limit=2,
        )
        self.assertEqual(cast, ("xun_yu", "xiahou_dun"))

    def test_select_cast_forced_exceeds_limit(self):
        state = build_initial_state()
        # 3 forced officers, 1 requested, limit=2.
        # Forced takes all spots, requested is dropped, only first 2 forced kept.
        cast = select_cast(
            state,
            "faction_1",
            requested=("dian_wei",),
            forced=("xun_yu", "xiahou_dun", "yu_jin"),
            limit=2,
        )
        self.assertEqual(cast, ("xun_yu", "xiahou_dun"))

    def test_select_cast_city_strongest_then_remaining(self):
        state = build_initial_state()
        # faction_1 cities in initial state:
        # chenliu: cao_ren (50+80+80=210), li_dian (60+70+70=200) -> best: cao_ren
        # xiangyang: yue_jin (55+80+72=207), cheng_yu (60+75+68=203) -> best: yue_jin
        # xuchang: xiahou_dun (210), yu_jin (201), dian_wei (185), xun_yu (185) -> best: xiahou_dun
        # When forced and requested are empty, limit=3:
        # Should pick best from chenliu, xiangyang, xuchang (cities ordered by city_id):
        # chenliu -> cao_ren, xiangyang -> yue_jin, xuchang -> xiahou_dun.
        cast = select_cast(state, "faction_1", requested=(), forced=(), limit=3)
        self.assertEqual(cast, ("cao_ren", "yue_jin", "xiahou_dun"))

    def test_frontier_fog_of_war_5_cities(self):
        state = build_initial_state()
        # In initial state:
        # faction_3 (Sun Quan) owns jianye.
        # jianye connects ONLY to xiangyang.
        # xiangyang is owned by faction_1 (曹操).
        # luoyang is owned by faction_2 (劉備).
        # xuchang and chenliu are owned by faction_1.
        # From faction_3's perspective:
        # - xiangyang is enemy and adjacent -> MUST be in frontier
        # - luoyang, xuchang, chenliu are enemy but NOT adjacent to jianye -> MUST NOT be in frontier
        view = build_faction_view(state, "faction_3", cast_ids=("zhou_yu",))
        frontier_ids = [f["id"] for f in view.frontier]
        self.assertEqual(frontier_ids, ["xiangyang"])

        xy_frontier = view.frontier[0]
        self.assertEqual(xy_frontier["owner"], "faction_1")
        self.assertEqual(xy_frontier["adjacent_to"], ["jianye"])
        self.assertIn("defense", xy_frontier)
        self.assertIn("troops", xy_frontier)

    def test_cast_and_roster_are_disjoint_and_roster_complete(self):
        state = build_initial_state()
        # faction_1 has 8 officers in total.
        # Put 2 in cast: xun_yu (xuchang), cao_ren (chenliu).
        view = build_faction_view(state, "faction_1", cast_ids=("xun_yu", "cao_ren"))
        cast_ids = {c["id"] for c in view.cast}
        self.assertEqual(cast_ids, {"xun_yu", "cao_ren"})

        # Collect all officers present in roster across all cities
        roster_names = set()
        for city_id, names in view.roster.items():
            for name in names:
                roster_names.add(name)

        # Cast officers' names must NOT be in roster
        self.assertNotIn("荀彧", roster_names)
        self.assertNotIn("曹仁", roster_names)

        # The other 6 living officers of faction_1 must be in roster
        remaining_names = {
            state.officer(oid).name
            for oid in ("xiahou_dun", "yu_jin", "dian_wei", "li_dian", "yue_jin", "cheng_yu")
        }
        self.assertEqual(roster_names, remaining_names)

    def test_to_dict_json_serializable(self):
        state = build_initial_state()
        view = build_faction_view(
            state,
            "faction_1",
            cast_ids=("xun_yu",),
            feedback=("some feedback",),
        )
        d = view.to_dict()
        dumped = json.dumps(d, ensure_ascii=False)
        self.assertIsInstance(dumped, str)
        self.assertIsInstance(d["cities"], list)
        self.assertIsInstance(d["frontier"], list)
        self.assertIsInstance(d["cast"], list)
        self.assertIsInstance(d["roster"], dict)
        self.assertIsInstance(d["roster"]["xuchang"], list)
        self.assertIsInstance(d["feedback"], list)

    def test_describe_events_filters_visible_and_takes_last_n(self):
        state = build_initial_state()
        # faction_1: owns xuchang, chenliu, xiangyang.
        # frontier for faction_1: luoyang (adjacent to xuchang/xiangyang), jianye (adjacent to xiangyang).
        # Create events:
        # Event 1: faction_1 actor (always visible)
        # Event 2: faction_2 in luoyang (in frontier -> visible)
        # Event 3: irrelevant event in an imaginary faraway city not adjacent to any friendly city
        # To test, let's create a custom state with a distant city
        distant_city = state.cities["luoyang"].__class__(
            "chengdu", "成都", "faction_2", 100, 100, 100, 100, 100, 100
        )
        new_cities = dict(state.cities)
        new_cities["chengdu"] = distant_city
        custom_state = state.__class__(**{**state.__dict__, "cities": new_cities})

        events = []
        for turn in range(1, 16):
            events.append(
                ResolutionEvent(
                    turn=turn,
                    officer_id="xun_yu",
                    faction_id="faction_1",
                    action="develop_agri",
                    city_id="xuchang",
                    detail=f"gain {turn}",
                )
            )
        # Irrelevant event
        events.append(
            ResolutionEvent(
                turn=16,
                officer_id="zhuge_liang",
                faction_id="faction_2",
                action="develop_agri",
                city_id="chengdu",
                detail="hidden in fog",
            )
        )

        described = describe_events(events, custom_state, "faction_1", limit=5)
        # Should retain only the last 5 visible events (turns 11..15)
        self.assertEqual(len(described), 5)
        self.assertTrue(described[-1].startswith("T15 荀彧 develop_agri@許昌: gain 15"))
        self.assertTrue(described[0].startswith("T11 荀彧 develop_agri@許昌: gain 11"))
        # Event 16 in chengdu must not be included
        for d in described:
            self.assertNotIn("chengdu", d)
            self.assertNotIn("成都", d)

    def test_describe_events_fallback_officer_id(self):
        state = build_initial_state()
        event = ResolutionEvent(
            turn=1,
            officer_id="ghost_officer",
            faction_id="faction_1",
            action="rest",
            city_id="xuchang",
            detail="rest",
        )
        desc = describe_events([event], state, "faction_1", limit=1)
        self.assertEqual(len(desc), 1)
        self.assertIn("ghost_officer", desc[0])

    def test_forced_cast_siege_target_and_captured(self):
        state = build_initial_state()
        # chenliu has cao_ren and li_dian.
        # Event 1: siege by faction_2 targeting chenliu. Both cao_ren and li_dian are in chenliu.
        ev_siege = ResolutionEvent(
            turn=1,
            officer_id="guan_yu",
            faction_id="faction_2",
            action="siege",
            city_id="chenliu",
            detail="attacking chenliu",
        )
        # Event 2: siege by faction_1 targeting luoyang (own faction action should NOT force)
        ev_own = ResolutionEvent(
            turn=1,
            officer_id="xiahou_dun",
            faction_id="faction_1",
            action="siege",
            city_id="luoyang",
            detail="we attack",
        )
        # Event 3: capture event containing xun_yu
        ev_capture = ResolutionEvent(
            turn=1,
            officer_id="guan_yu",
            faction_id="faction_2",
            action="siege",
            city_id="luoyang",
            detail="captured officer",
            captured_officers=("xun_yu",),
        )

        forced = forced_cast(state, "faction_1", [ev_siege, ev_own, ev_capture])
        # cao_ren and li_dian in chenliu, plus xun_yu captured
        self.assertEqual(forced, ("cao_ren", "li_dian", "xun_yu"))

    def test_build_faction_view_ignores_other_faction_cast_ids(self):
        state = build_initial_state()
        # zhuge_liang is faction_2
        view = build_faction_view(
            state,
            "faction_1",
            cast_ids=("zhuge_liang", "xun_yu"),
        )
        cast_ids = [c["id"] for c in view.cast]
        self.assertEqual(cast_ids, ["xun_yu"])

    def test_build_faction_view_feedback_truncation(self):
        state = build_initial_state()
        feedbacks = [f"feedback {i}" for i in range(20)]
        view = build_faction_view(
            state,
            "faction_1",
            cast_ids=("xun_yu",),
            feedback=feedbacks,
        )
        self.assertEqual(len(view.feedback), EVENT_LIMIT)
        self.assertEqual(view.feedback, tuple(feedbacks[:EVENT_LIMIT]))


if __name__ == "__main__":
    unittest.main()
