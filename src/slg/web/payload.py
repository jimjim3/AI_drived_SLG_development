"""JSON payloads for the web UI. Built only from a FactionView plus the officer's own legal actions,
so the player never sees more than an AI faction agent would."""

from __future__ import annotations

from ..engine.legal_actions import generate_legal_actions
from ..engine.view import FactionView
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
    return d
