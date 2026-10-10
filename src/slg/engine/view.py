"""Faction-level narrative view construction and utilities.

In faction narrative mode, agents receive a restricted view of the game state
rather than the full GameState. Fog of war prevents seeing non-adjacent enemy
cities, and cast selection bounds the input token budget per turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..schema import (
    CAST_LIMIT,
    EVENT_LIMIT,
    GameState,
    LegalAction,
    NEGLECT_PETITION,
    PETITION_LOYALTY_BELOW,
    ResolutionEvent,
)
from .legal_actions import generate_legal_actions


@dataclass(frozen=True)
class FactionView:
    turn: int
    faction_id: str
    faction_name: str
    cities: tuple
    frontier: tuple
    cast: tuple
    roster: Mapping[str, tuple]
    events: tuple = ()
    feedback: tuple = ()

    def to_dict(self) -> dict:
        """Return pure JSON-serializable representation of this view."""
        return {
            "turn": self.turn,
            "faction_id": self.faction_id,
            "faction_name": self.faction_name,
            "cities": [dict(c) for c in self.cities],
            "frontier": [dict(f) for f in self.frontier],
            "cast": [dict(c) for c in self.cast],
            "roster": {cid: list(names) for cid, names in self.roster.items()},
            "events": list(self.events),
            "feedback": list(self.feedback),
        }


def _fmt_num(val: float | int | None) -> str:
    if val is None:
        return ""
    if isinstance(val, (int, float)) and val == int(val):
        return str(int(val))
    return str(val)


def format_legal(la: LegalAction) -> str:
    """Format a LegalAction into a compact string representation.

    - No params: "develop_agri"
    - Numeric params: "recruit troops=100..1200/100" (min..max/step)
    - Discrete params: "move to=[chenliu,xiangyang]"
    - Multiple params joined with space: "siege to=[luoyang] troops=500..1100/100"
    """
    if not la.params:
        return la.action
    parts = [la.action]
    for pname, ps in la.params.items():
        if ps.is_discrete():
            choices_str = ",".join(str(c) for c in (ps.choices or ()))
            parts.append(f"{pname}=[{choices_str}]")
        else:
            min_str = _fmt_num(ps.min)
            max_str = _fmt_num(ps.max)
            if ps.step is not None:
                step_str = _fmt_num(ps.step)
                parts.append(f"{pname}={min_str}..{max_str}/{step_str}")
            else:
                parts.append(f"{pname}={min_str}..{max_str}")
    return " ".join(parts)


def select_cast(
    state: GameState,
    faction_id: str,
    requested: Sequence[str] = (),
    forced: Sequence[str] = (),
    limit: int = CAST_LIMIT,
) -> tuple[str, ...]:
    """Select up to ``limit`` officers for active cast spotlight.

    Priority order:
    1. forced officers (filtered to living members of this faction, deduped)
    2. requested officers (filtered to living members, deduped)
    3. highest politics+war+leadership officer from each friendly city (sorted by city_id)
    4. remaining officers of the faction sorted by (-(politics+war+leadership), officer_id)
    5. truncated to ``limit`` (forced officers are never displaced by requested).
    """
    def is_eligible(oid: str) -> bool:
        o = state.officers.get(oid)
        return o is not None and o.faction_id == faction_id and o.is_alive

    result: list[str] = []
    seen: set[str] = set()

    def add(oid: str) -> None:
        if oid not in seen and is_eligible(oid):
            seen.add(oid)
            result.append(oid)

    for oid in forced:
        add(oid)

    for oid in requested:
        add(oid)

    if len(result) < limit:
        friendly_cities = sorted(state.cities_of(faction_id), key=lambda c: c.city_id)
        for c in friendly_cities:
            city_officers = [
                o for o in state.officers.values()
                if o.faction_id == faction_id and o.city_id == c.city_id and o.is_alive
            ]
            if city_officers:
                best = min(
                    city_officers,
                    key=lambda o: (-(o.politics + o.war + o.leadership), o.officer_id),
                )
                add(best.officer_id)

    if len(result) < limit:
        remaining_officers = sorted(
            [
                o for o in state.officers.values()
                if o.faction_id == faction_id and o.is_alive and o.officer_id not in seen
            ],
            key=lambda o: (-(o.politics + o.war + o.leadership), o.officer_id),
        )
        for o in remaining_officers:
            add(o.officer_id)

    return tuple(result[:limit])


def describe_events(
    events: Sequence[ResolutionEvent],
    state: GameState,
    faction_id: str,
    limit: int = EVENT_LIMIT,
) -> tuple[str, ...]:
    """Filter and describe recent resolution events visible to this faction.

    Keeps events where the actor belongs to this faction, or where the target/city
    belongs to this faction or its frontier. Returns up to the last ``limit`` events.
    """
    friendly_cids = {c.city_id for c in state.cities.values() if c.owner == faction_id}
    frontier_cids = {
        c.city_id
        for c in state.cities.values()
        if c.owner != faction_id
        and any(nid in friendly_cids for nid in state.adjacency.get(c.city_id, ()))
    }
    relevant_cids = friendly_cids | frontier_cids

    matched: list[str] = []
    for ev in events:
        actor_is_faction = ev.faction_id == faction_id
        target_in_relevant = (
            ev.city_id in relevant_cids
            or (ev.captured_city is not None and ev.captured_city in relevant_cids)
        )
        if actor_is_faction or target_in_relevant:
            officer = state.officers.get(ev.officer_id)
            officer_name = officer.name if officer is not None else ev.officer_id
            city = state.cities.get(ev.city_id)
            city_name = city.name if city is not None else ev.city_id
            desc = f"T{ev.turn} {officer_name} {ev.action}@{city_name}: {ev.detail}"
            matched.append(desc)

    if limit <= 0:
        return ()
    return tuple(matched[-limit:])


def forced_cast(
    state: GameState,
    faction_id: str,
    events: Sequence[ResolutionEvent],
) -> tuple[str, ...]:
    """Return officers forced into cast due to siege, capture events, or neglected petition."""
    forced: set[str] = set()
    for o in state.officers.values():
        if o.faction_id != faction_id or not o.is_alive:
            continue

        is_siege_target = any(
            ev.action == "siege"
            and ev.faction_id != faction_id
            and ev.city_id == o.city_id
            for ev in events
        )

        is_captured = any(
            o.officer_id in (getattr(ev, "captured_officers", ()) or ())
            for ev in events
        )

        if is_siege_target or is_captured:
            forced.add(o.officer_id)

    siege_officers = sorted(forced)

    petition_officers = [
        o
        for o in state.officers.values()
        if o.faction_id == faction_id
        and o.is_alive
        and o.officer_id not in forced
        and o.neglect >= NEGLECT_PETITION
        and o.loyalty < PETITION_LOYALTY_BELOW
    ]
    petition_officers.sort(key=lambda o: (-o.neglect, o.officer_id))

    result = siege_officers + [o.officer_id for o in petition_officers]
    return tuple(result[:CAST_LIMIT])


def build_faction_view(
    state: GameState,
    faction_id: str,
    cast_ids: Sequence[str],
    events: Sequence[ResolutionEvent] = (),
    feedback: Sequence[str] = (),
) -> FactionView:
    """Construct a FactionView for the specified faction."""
    friendly_cities = sorted(state.cities_of(faction_id), key=lambda c: c.city_id)
    friendly_cids = {c.city_id for c in friendly_cities}

    cities_data = []
    for c in friendly_cities:
        neighbors = [
            f"{nid}:{state.city(nid).owner}"
            for nid in sorted(state.adjacency.get(c.city_id, ()))
        ]
        cities_data.append({
            "id": c.city_id,
            "name": c.name,
            "agri": c.agriculture,
            "commerce": c.commerce,
            "defense": c.defense,
            "gold": c.gold,
            "food": c.food,
            "troops": c.troops,
            "neighbors": neighbors,
        })

    frontier_cities = sorted(
        [
            c
            for c in state.cities.values()
            if c.owner != faction_id
            and any(nid in friendly_cids for nid in state.adjacency.get(c.city_id, ()))
        ],
        key=lambda c: c.city_id,
    )
    frontier_data = []
    for ec in frontier_cities:
        adj = sorted(nid for nid in state.adjacency.get(ec.city_id, ()) if nid in friendly_cids)
        frontier_data.append({
            "id": ec.city_id,
            "name": ec.name,
            "owner": ec.owner,
            "troops": ec.troops,
            "defense": ec.defense,
            "adjacent_to": adj,
        })

    cast_data = []
    cast_set = set()
    for oid in cast_ids:
        if oid in cast_set:
            continue
        o = state.officers.get(oid)
        if o is None or o.faction_id != faction_id or not o.is_alive:
            continue
        cast_set.add(oid)
        legal_actions = generate_legal_actions(state, o)
        legal_formatted = [format_legal(la) for la in legal_actions]
        cast_data.append({
            "id": o.officer_id,
            "name": o.name,
            "city": o.city_id,
            "politics": o.politics,
            "war": o.war,
            "leadership": o.leadership,
            "loyalty": o.loyalty,
            "ambition": o.ambition,
            "neglect": o.neglect,
            "legal": legal_formatted,
        })

    roster_data = {}
    for c in friendly_cities:
        non_cast = sorted(
            [
                o
                for o in state.officers.values()
                if o.faction_id == faction_id
                and o.is_alive
                and o.city_id == c.city_id
                and o.officer_id not in cast_set
            ],
            key=lambda o: o.officer_id,
        )
        roster_data[c.city_id] = tuple(o.name for o in non_cast)

    described_events = describe_events(events, state, faction_id, limit=EVENT_LIMIT)
    trimmed_feedback = tuple(feedback[:EVENT_LIMIT])

    return FactionView(
        turn=state.turn,
        faction_id=faction_id,
        faction_name=state.faction(faction_id).name,
        cities=tuple(cities_data),
        frontier=tuple(frontier_data),
        cast=tuple(cast_data),
        roster=roster_data,
        events=described_events,
        feedback=trimmed_feedback,
    )
