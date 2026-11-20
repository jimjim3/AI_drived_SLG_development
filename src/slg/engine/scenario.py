"""Scenario format v1: validate a scenario document and build a GameState from it.

The format is specified in docs/SCENARIO_FORMAT.md. This module only knows the format; it does not
change how the built-in scenarios work (initial_state.py still builds those). Fields the engine cannot
act on yet (events, neutral cities, other victory types) are either validated for shape and carried in
the returned metadata, or rejected with an explicit "not supported yet" error, never silently ignored.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import CityState, FactionState, GameState, OfficerState
from . import combat

FORMAT = 1
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
VERIFICATION = ("unverified", "verified", "game_design")
VICTORY_TYPES = ("most_cities",)  # reserved: capture_capital, unify (see docs/SCENARIO_FORMAT.md)
CITY_NUMS = ("agriculture", "commerce", "defense", "gold", "food", "troops")
OFFICER_STATS = ("politics", "war", "leadership")
DEFAULT_LOYALTY = 80
DEFAULT_AMBITION = 50


class ScenarioError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""))


@dataclass(frozen=True)
class ScenarioMeta:
    id: str
    name_zh: str
    year: int
    summary_zh: str
    verification: str
    rules: str | None
    victory: dict
    capitals: dict  # faction_id -> city_id
    playable: tuple  # faction ids a human may pick
    positions: dict  # city_id -> (x, y)
    events: tuple = field(default_factory=tuple)  # carried, not yet executed by the engine


def _is_int(v, lo=0, hi=None) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= lo and (hi is None or v <= hi)


def validate(doc) -> list[str]:
    """All problems found in ``doc`` (empty list = valid). Never raises on bad input."""
    p: list[str] = []
    if not isinstance(doc, dict):
        return ["scenario must be an object"]
    if doc.get("format") != FORMAT:
        return [f"unsupported format {doc.get('format')!r} (expected {FORMAT})"]
    for key in ("id", "name_zh"):
        if not isinstance(doc.get(key), str) or not doc[key]:
            p.append(f"{key} must be a non-empty string")
    if isinstance(doc.get("id"), str) and not ID_RE.match(doc["id"]):
        p.append(f"id {doc['id']!r} must match {ID_RE.pattern}")
    if not _is_int(doc.get("year"), 1, 2000):
        p.append("year must be an integer (1..2000)")
    if doc.get("verification") not in VERIFICATION:
        p.append(f"verification must be one of {VERIFICATION}")
    rules = doc.get("rules")
    if rules is not None and rules not in combat.RULESETS:
        p.append(f"unknown ruleset {rules!r}")

    # --- map ---
    m = doc.get("map") if isinstance(doc.get("map"), dict) else {}
    map_cities = m.get("cities") if isinstance(m.get("cities"), list) else []
    if not map_cities:
        p.append("map.cities must be a non-empty list")
    city_ids: list[str] = []
    for c in map_cities:
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not ID_RE.match(cid):
            p.append(f"bad city id {cid!r}")
            continue
        if cid in city_ids:
            p.append(f"duplicate city id {cid!r}")
        city_ids.append(cid)
        if not isinstance(c.get("name_zh"), str) or not c["name_zh"]:
            p.append(f"city {cid}: name_zh required")
        pos = c.get("pos")
        if not (isinstance(pos, list) and len(pos) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in pos)):
            p.append(f"city {cid}: pos must be [x, y]")
    known = set(city_ids)
    adj: dict[str, set[str]] = {c: set() for c in known}
    seen_edges = set()
    for e in m.get("edges", []) if isinstance(m.get("edges"), list) else []:
        if not (isinstance(e, list) and len(e) == 2 and all(isinstance(x, str) for x in e)):
            p.append(f"bad edge {e!r}")
            continue
        a, b = e
        if a == b or a not in known or b not in known:
            p.append(f"edge {a}-{b}: needs two different known cities")
            continue
        k = tuple(sorted(e))
        if k in seen_edges:
            p.append(f"duplicate edge {a}-{b}")
        seen_edges.add(k)
        adj[a].add(b)
        adj[b].add(a)
    if known:
        start = next(iter(city_ids))
        reach, q = {start}, deque([start])
        while q:
            for n in adj[q.popleft()]:
                if n not in reach:
                    reach.add(n)
                    q.append(n)
        if reach != known:
            p.append(f"map is not connected; unreachable from {start}: {sorted(known - reach)[:5]}")

    # --- factions ---
    facs = doc.get("factions") if isinstance(doc.get("factions"), list) else []
    fids: list[str] = []
    for f in facs:
        fid = f.get("id") if isinstance(f, dict) else None
        if not isinstance(fid, str) or not ID_RE.match(fid):
            p.append(f"bad faction id {fid!r}")
            continue
        if fid in fids:
            p.append(f"duplicate faction id {fid!r}")
        fids.append(fid)
        if not isinstance(f.get("name_zh"), str) or not f["name_zh"]:
            p.append(f"faction {fid}: name_zh required")
        if not isinstance(f.get("playable"), bool):
            p.append(f"faction {fid}: playable must be true/false")
    if len(fids) < 2:
        p.append("at least 2 factions are required")

    # --- cities ---
    owner: dict[str, str] = {}
    for c in doc.get("cities", []) if isinstance(doc.get("cities"), list) else []:
        cid = c.get("id") if isinstance(c, dict) else None
        if cid not in known:
            p.append(f"cities: unknown city {cid!r}")
            continue
        if cid in owner:
            p.append(f"cities: duplicate entry for {cid}")
        o = c.get("owner")
        if o is None or o == "neutral":
            p.append(f"city {cid}: neutral cities are not supported by the engine yet (owner must be a faction)")
        elif o not in fids:
            p.append(f"city {cid}: unknown owner {o!r}")
        owner[cid] = o
        for k in CITY_NUMS:
            if not _is_int(c.get(k)):
                p.append(f"city {cid}: {k} must be a non-negative integer")
    for cid in sorted(known - set(owner)):
        p.append(f"city {cid} has no state entry in 'cities'")
    for f in facs:
        fid = f.get("id") if isinstance(f, dict) else None
        if fid in fids:
            if not any(o == fid for o in owner.values()):
                p.append(f"faction {fid} owns no city")
            cap = f.get("capital")
            if cap not in known:
                p.append(f"faction {fid}: capital {cap!r} is not a map city")
            elif owner.get(cap) != fid:
                p.append(f"faction {fid}: capital {cap} is not owned by it")

    # --- officers ---
    oids, per_faction = set(), {f: 0 for f in fids}
    for o in doc.get("officers", []) if isinstance(doc.get("officers"), list) else []:
        oid = o.get("id") if isinstance(o, dict) else None
        if not isinstance(oid, str) or not ID_RE.match(oid):
            p.append(f"bad officer id {oid!r}")
            continue
        if oid in oids:
            p.append(f"duplicate officer id {oid!r}")
        oids.add(oid)
        if not isinstance(o.get("name_zh"), str) or not o["name_zh"]:
            p.append(f"officer {oid}: name_zh required")
        fid, cid = o.get("faction"), o.get("city")
        if fid not in fids:
            p.append(f"officer {oid}: unknown faction {fid!r}")
        else:
            per_faction[fid] += 1
        if cid not in known:
            p.append(f"officer {oid}: unknown city {cid!r}")
        elif fid in fids and owner.get(cid) != fid:
            p.append(f"officer {oid}: city {cid} is not owned by faction {fid}")
        for k in OFFICER_STATS:
            if not _is_int(o.get(k), 0, 100):
                p.append(f"officer {oid}: {k} must be an integer 0..100")
        for k in ("loyalty", "ambition"):
            if k in o and not _is_int(o[k], 0, 100):
                p.append(f"officer {oid}: {k} must be an integer 0..100")
    for fid, n in per_faction.items():
        if n == 0:
            p.append(f"faction {fid} has no officers")

    # --- events (shape only; the engine does not run them yet) ---
    ev_ids = set()
    for e in doc.get("events", []) if isinstance(doc.get("events"), list) else []:
        eid = e.get("id") if isinstance(e, dict) else None
        if not isinstance(eid, str) or not eid:
            p.append("event needs a string id")
            continue
        if eid in ev_ids:
            p.append(f"duplicate event id {eid!r}")
        ev_ids.add(eid)
        if not _is_int(e.get("turn"), 1):
            p.append(f"event {eid}: turn must be an integer >= 1")
        if not isinstance(e.get("text_zh"), str) or not e["text_zh"]:
            p.append(f"event {eid}: text_zh required")

    # --- victory ---
    v = doc.get("victory")
    if not isinstance(v, dict) or v.get("type") not in VICTORY_TYPES:
        p.append(f"victory.type must be one of {VICTORY_TYPES} (others are reserved, not implemented)")
    elif not _is_int(v.get("turns"), 1, 400):
        p.append("victory.turns must be an integer 1..400")
    return p


def build(doc: dict) -> tuple[GameState, ScenarioMeta]:
    """Validate then build a turn-0 GameState plus metadata. Raises ScenarioError listing every problem."""
    problems = validate(doc)
    if problems:
        raise ScenarioError(problems)
    names = {c["id"]: c["name_zh"] for c in doc["map"]["cities"]}
    cities = {
        c["id"]: CityState(c["id"], names[c["id"]], c["owner"], *(c[k] for k in CITY_NUMS))
        for c in doc["cities"]
    }
    factions = {f["id"]: FactionState(f["id"], f["name_zh"], True) for f in doc["factions"]}
    officers = {
        o["id"]: OfficerState(o["id"], o["name_zh"], o["faction"], o["city"], o["politics"], o["war"], o["leadership"],
                              o.get("loyalty", DEFAULT_LOYALTY), o.get("ambition", DEFAULT_AMBITION))
        for o in doc["officers"]
    }
    adj: dict[str, set[str]] = {cid: set() for cid in names}
    for a, b in doc["map"]["edges"]:
        adj[a].add(b)
        adj[b].add(a)
    state = GameState(turn=0, factions=factions, cities=cities, officers=officers,
                      adjacency={cid: tuple(sorted(n)) for cid, n in adj.items()})
    meta = ScenarioMeta(
        id=doc["id"], name_zh=doc["name_zh"], year=doc["year"], summary_zh=doc.get("summary_zh", ""),
        verification=doc["verification"], rules=doc.get("rules"), victory=dict(doc["victory"]),
        capitals={f["id"]: f["capital"] for f in doc["factions"]},
        playable=tuple(f["id"] for f in doc["factions"] if f["playable"]),
        positions={c["id"]: tuple(c["pos"]) for c in doc["map"]["cities"]},
        events=tuple(doc.get("events", [])),
    )
    return state, meta


def load(path: str | Path) -> tuple[GameState, ScenarioMeta]:
    with open(path, encoding="utf-8") as f:
        return build(json.load(f))
