"""Alliances between factions (phase 1 of docs/DESIGN_ALLIANCE.md).

Only active under rulesets with ``alliance`` on; under every other ruleset the state's ``diplomacy`` stays empty and
nothing here changes behaviour. Phase 1: friendship, propose / break, no mutual sieges, shared vision, betrayal
penalty. Collateral, officer exchange and mutual aid come later.
"""

from __future__ import annotations

from dataclasses import replace

from ..schema import Diplomacy, GameState, pair_key
from . import combat

DEFAULT_FRIENDSHIP = 50      # between factions with no history
PEACE_CAP = 60               # peace alone never raises friendship above this
ACCEPT_THRESHOLD = 50        # the rule AI accepts a proposal at or above this friendship
SIEGE_PENALTY = 20           # an attack costs the pair this much friendship
DECAY_EVERY = 3              # an alliance loses 1 friendship every this many turns
DISSOLVE_BELOW = 20          # friendship this low ends the alliance quietly
REJECT_COOLDOWN = 3
PLEDGE_BONUS = 5             # each 100 gold pledged counts as this much extra friendship when judging a proposal


def enabled() -> bool:
    return combat.active().alliance


def friendship(state: GameState, a: str, b: str) -> int:
    return state.diplomacy.friendship.get(pair_key(a, b), DEFAULT_FRIENDSHIP)


def allied(state: GameState, a: str, b: str) -> bool:
    return a != b and pair_key(a, b) in state.diplomacy.alliances


def allies_of(state: GameState, fid: str) -> list[str]:
    out = []
    for key in state.diplomacy.alliances:
        x, y = key.split("|")
        if fid in (x, y):
            out.append(y if x == fid else x)
    return sorted(out)


def envoy_id(state: GameState, fid: str) -> str | None:
    """The one officer per faction who handles diplomacy: highest politics, lowest id on ties."""
    cands = [o for o in state.officers.values() if o.faction_id == fid and o.is_alive]
    if not cands:
        return None
    return min(cands, key=lambda o: (-o.politics, o.officer_id)).officer_id


def can_propose(state: GameState, proposer: str, target: str) -> bool:
    key = pair_key(proposer, target)
    return (
        proposer != target
        and state.factions[target].is_active
        and key not in state.diplomacy.alliances
        and state.turn > state.diplomacy.cooldown.get(key, -1)
    )


def default_accept(state: GameState, proposer: str, target: str, pledge: int = 0) -> bool:
    """Rule-AI judgement; an LLM faction may override it via ``respond_alliance``."""
    return friendship(state, proposer, target) + pledge // 100 * PLEDGE_BONUS >= ACCEPT_THRESHOLD


def _with(state: GameState, **fields) -> GameState:
    d = state.diplomacy
    return replace(state, diplomacy=Diplomacy(
        friendship=fields.get("friendship", dict(d.friendship)),
        alliances=fields.get("alliances", dict(d.alliances)),
        cooldown=fields.get("cooldown", dict(d.cooldown)),
        collateral=fields.get("collateral", dict(d.collateral)),
    ))


def collateral_of(state: GameState, a: str, b: str) -> tuple | None:
    return state.diplomacy.collateral.get(pair_key(a, b))


def _credit(state: GameState, fid: str, gold: int) -> GameState:
    """Pay gold into the faction's richest city (lowest id on ties)."""
    cities = state.cities_of(fid)
    if not cities or gold <= 0:
        return state
    c = min(cities, key=lambda c: (-c.gold, c.city_id))
    ncs = dict(state.cities)
    ncs[c.city_id] = replace(c, gold=c.gold + gold)
    return replace(state, cities=ncs)


def _settle(state: GameState, key: str, to: str | None) -> GameState:
    """Release the collateral held for a pair: to ``to`` (None = back to the depositor)."""
    held = dict(state.diplomacy.collateral)
    entry = held.pop(key, None)
    state = _with(state, collateral=held)
    if entry:
        depositor, gold = entry
        state = _credit(state, to or depositor, gold)
    return state


def adjust(state: GameState, a: str, b: str, delta: int) -> GameState:
    fr = dict(state.diplomacy.friendship)
    key = pair_key(a, b)
    fr[key] = max(0, min(100, fr.get(key, DEFAULT_FRIENDSHIP) + delta))
    return _with(state, friendship=fr)


def propose(state: GameState, proposer: str, target: str, accept: bool,
            pledge: int = 0, origin_city: str | None = None) -> GameState:
    key = pair_key(proposer, target)
    if accept:
        if pledge and origin_city:
            ncs = dict(state.cities)
            ncs[origin_city] = replace(ncs[origin_city], gold=ncs[origin_city].gold - pledge)
            held = dict(state.diplomacy.collateral)
            held[key] = (proposer, pledge)
            state = replace(_with(state, collateral=held), cities=ncs)
        al = dict(state.diplomacy.alliances)
        al[key] = state.turn
        fr = dict(state.diplomacy.friendship)
        fr[key] = max(fr.get(key, DEFAULT_FRIENDSHIP), 60)  # a fresh alliance starts at the baseline
        return _with(state, alliances=al, friendship=fr)
    cd = dict(state.diplomacy.cooldown)
    cd[key] = state.turn + REJECT_COOLDOWN
    return _with(state, cooldown=cd)


def break_alliance(state: GameState, breaker: str, victim: str) -> GameState:
    """Betrayal: the abandoned partner and every other ally of the breaker lose friendship."""
    victim_loss, other_loss, cooldown = combat.active().ally_break
    others = [f for f in allies_of(state, breaker) if f != victim]
    al = dict(state.diplomacy.alliances)
    al.pop(pair_key(breaker, victim), None)
    cd = dict(state.diplomacy.cooldown)
    cd[pair_key(breaker, victim)] = state.turn + cooldown
    state = _with(state, alliances=al, cooldown=cd)
    held = state.diplomacy.collateral.get(pair_key(breaker, victim))
    if held:  # the depositor betraying forfeits it to the victim; the holder betraying gives it back
        state = _settle(state, pair_key(breaker, victim), victim if held[0] == breaker else None)
    state = adjust(state, breaker, victim, -victim_loss)
    for f in others:
        state = adjust(state, breaker, f, -other_loss)
    return state


def on_siege(state: GameState, attacker: str, defender: str) -> GameState:
    return adjust(state, attacker, defender, -SIEGE_PENALTY)


def tick(state: GameState) -> GameState:
    """Turn-start upkeep: peace slowly warms strangers, alliances cool and may lapse."""
    fids = sorted(f for f, fs in state.factions.items() if fs.is_active)
    for i, a in enumerate(fids):
        for b in fids[i + 1:]:
            key = pair_key(a, b)
            if key in state.diplomacy.alliances:
                if state.turn % DECAY_EVERY == 0:
                    state = adjust(state, a, b, -1)
                if friendship(state, a, b) < DISSOLVE_BELOW:
                    al = dict(state.diplomacy.alliances)
                    al.pop(key, None)
                    state = _settle(_with(state, alliances=al), key, None)
            elif friendship(state, a, b) < PEACE_CAP:
                state = adjust(state, a, b, 1)
    return state


def allied_sight(state: GameState, fid: str) -> set[str]:
    """Cities a faction sees through its allies: their cities and everything next to them."""
    seen: set[str] = set()
    for ally in allies_of(state, fid):
        for c in state.cities_of(ally):
            seen.add(c.city_id)
            seen.update(state.adjacency.get(c.city_id, ()))
    return seen
