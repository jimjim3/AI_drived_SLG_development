"""JSON payloads for the web UI. Built only from a FactionView plus the officer's own legal actions,
so the player never sees more than an AI faction agent would."""

from __future__ import annotations

from .. import narrative
from ..engine.initial_state import FACTION_IDS, parse_scenario, resolve_scenario
from ..engine.legal_actions import generate_legal_actions
from ..engine.view import FactionView, relevant_events
from ..schema import GameState

# Public geography (not hidden information): city -> (x, y) on an 11 x 8.5 canvas.
CITY_POS = {
    "hanzhong": (1.4, 2.6), "wancheng": (3.4, 3.8), "luoyang": (4.2, 6.4),
    "chenliu": (7.2, 7.2), "xuchang": (7.0, 4.8), "xiangyang": (5.6, 2.2),
    "jianye": (8.8, 3.4), "wujun": (9.8, 2.1), "kuaiji": (9.8, 0.7),
}


def _param(p) -> dict:
    d = {"name": p.name}
    for k in ("min", "max", "step"):
        if getattr(p, k) is not None:
            d[k] = getattr(p, k)
    if p.choices is not None:
        d["choices"] = list(p.choices)
    return d


def legal_structured(state: GameState, officer_id: str) -> list[dict]:
    off = state.officers[officer_id]
    return [
        {"action": la.action, "params": {k: _param(v) for k, v in la.params.items()},
         "cost": la.cost, "note": la.note}
        for la in generate_legal_actions(state, off)
    ]


def state_payload(state: GameState, view: FactionView) -> dict:
    own = {c["id"] for c in view.cities}
    seen = {f["id"] for f in view.frontier}
    edges = sorted({tuple(sorted((a, b))) for a, nb in state.adjacency.items() for b in nb})
    nodes = []
    for cid, (x, y) in CITY_POS.items():
        if cid in own:
            vis = "own"
        elif cid in seen:
            vis = "frontier"
        else:
            vis = "fog"
        nodes.append({"id": cid, "x": x, "y": y, "visibility": vis})
    d = view.to_dict()
    for c in d["cast"]:
        c["legal_structured"] = legal_structured(state, c["id"])
    by_name = {o.name: o for o in state.officers.values() if o.faction_id == view.faction_id and o.is_alive}
    d["roster_info"] = {
        cid: [{"id": by_name[n].officer_id, "name": n, "city": cid, "politics": by_name[n].politics,
               "war": by_name[n].war, "leadership": by_name[n].leadership, "loyalty": by_name[n].loyalty,
               "neglect": by_name[n].neglect} for n in names if n in by_name]
        for cid, names in view.roster.items()
    }
    d["map"] = {"nodes": nodes, "edges": [list(e) for e in edges]}
    # the first turn a player sees is turn 1; the calendar is 0-based, so spring opens the game
    d["calendar"] = narrative.calendar_label(max(state.turn - 1, 0))
    return d


def narrative_payload(scenario: str, faction_id: str) -> dict:
    """Story text for the chosen scenario and lord. Static, public history text (no game state),
    so it can be served before a game exists (setup-screen preview)."""
    if faction_id not in FACTION_IDS:
        raise ValueError(f"unknown faction {faction_id!r}")
    kind, _ = parse_scenario(scenario)  # validates the id
    n = narrative.load_narrative()
    return {
        "scenario": {"id": resolve_scenario(scenario, faction_id), "kind": kind, **narrative.scenario(kind)},
        "title": n["world"]["title"], "subtitle": n["world"]["subtitle"], "prologue": n["world"]["prologue"],
        "lord": narrative.lord(faction_id),
        "opening": narrative.opening(kind, faction_id),
        "cities": n["world"]["cities"],
        "officers": n["officers"],
    }


def story_lines(events, state: GameState, faction_id: str, limit: int = 12) -> list[str]:
    """Narrative sentences (zh-TW templates) for the sieges and incidents the player can see.

    Routine develop/recruit/move lines are left to the plain event list; only turning points are told.
    """
    def name_of(oid):
        o = state.officers.get(oid)
        return o.name if o else oid

    def city_name(cid):
        c = state.cities.get(cid)
        return c.name if c else cid

    lines = []
    for ev in relevant_events(events, state, faction_id):
        mine = ev.faction_id == faction_id
        if ev.action == "siege":
            target = city_name(ev.city_id)
            captured = ev.captured_city is not None
            if mine:
                key = "siege_captured" if captured else "siege_repelled"
                lines.append(narrative.render_event(key, ev.turn, officer=name_of(ev.officer_id), target=target))
            elif ev.defender_faction != faction_id:
                continue  # a siege between other factions; not ours to tell
            else:
                key = "city_lost" if captured else "siege_defended"
                lines.append(narrative.render_event(key, ev.turn, city=target))
        elif ev.action == "defect" and mine:
            fname = state.faction(ev.faction_id).name
            lines.append(narrative.render_event("defect", ev.turn, officer=name_of(ev.officer_id), faction=fname))
    return lines[-limit:]
