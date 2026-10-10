"""Game orchestration: decide, apply, step, run.

The :class:`Game` owns the mutable simulation handle. The state itself is an
immutable :class:`GameState` that is replaced (copy-on-write) on every action.
A deterministic, sequential order (factions by id, officers by id) plus a
seeded RNG make a full run reproducible.
"""

from __future__ import annotations

import random
from dataclasses import replace

from ..agents.rule_based import RuleBasedAgent
from ..schema import AgentDecision, GameState, LogEntry
from .legal_actions import generate_legal_actions
from .resolution import resolve_decision
from .validation import validate_decision


class Game:
    def __init__(self, state: GameState, agents_by_faction, rng: random.Random):
        self.state = state
        self.agents = agents_by_faction
        self.rng = rng
        self.stats = {"decisions": 0, "valid": 0, "rejected": 0, "fallbacks": 0}
        self.events: list = []
        self.log_entries: list = []
        self._fallback = RuleBasedAgent()

    # -- decision with safety net -----------------------------------------
    def decide(self, officer) -> tuple[AgentDecision, bool, str, int]:
        """Return ``(decision, fallback, agent_name, legal_count)``.

        Safety net: try the primary agent up to twice; on exception or
        validation failure record a rejection. After two primary failures fall
        back to the rule-based agent, and finally to a hardcoded ``rest``
        (always legal). This guarantees ``stats["valid"] == stats["decisions"]``.
        """
        self.stats["decisions"] += 1
        agent = self.agents.get(officer.faction_id)
        legal = generate_legal_actions(self.state, officer)
        legal_count = len(legal)
        agent_name = getattr(agent, "name", "agent") if agent is not None else "safety_net"

        # Primary agent: up to two attempts.
        for _ in range(2):
            try:
                decision = agent.decide(self.state, officer, legal)
            except Exception:
                self.stats["rejected"] += 1
                continue
            ok, _ = validate_decision(self.state, officer, decision)
            if ok:
                self.stats["valid"] += 1
                return (decision, False, agent_name, legal_count)
            self.stats["rejected"] += 1

        # Fallback: rule-based agent.
        self.stats["fallbacks"] += 1
        fallback = self._fallback.decide(self.state, officer, legal)
        ok, _ = validate_decision(self.state, officer, fallback)
        if ok:
            self.stats["valid"] += 1
            return (fallback, True, "rule_based", legal_count)

        # Last resort: hardcoded rest (always legal).
        self.stats["valid"] += 1
        return (AgentDecision(officer.officer_id, "rest"), True, "safety_net", legal_count)

    # -- apply / step / run ------------------------------------------------
    def apply(self, officer, decision: AgentDecision):
        new_state, event = resolve_decision(self.state, officer, decision, self.rng)
        self.state = new_state
        self.events.append(event)
        return event

    def step(self) -> GameState:
        """Run one full turn: income, then every active officer acts once.

        Factions act in a per-turn ``rng.shuffle``d order (sorted first) so
        that the seed influences who moves first.
        """
        self.state = apply_income(self.state, self.rng)
        order = sorted(self.state.factions)
        self.rng.shuffle(order)
        self.state = replace(self.state, turn=self.state.turn + 1)
        turn = self.state.turn

        for fid in order:
            faction = self.state.factions[fid]
            if not faction.is_active:
                continue
            if not self.state.cities_of(fid):
                continue  # eliminated mid-turn
            for oid in sorted(self.state.officers):
                officer = self.state.officers[oid]
                if officer.faction_id != fid or not officer.is_alive:
                    continue
                decision, fallback, agent_name, legal_count = self.decide(officer)
                event = self.apply(officer, decision)
                self.log_entries.append(LogEntry(
                    turn=turn,
                    officer_id=officer.officer_id,
                    faction_id=officer.faction_id,
                    agent_name=agent_name,
                    legal_count=legal_count,
                    action=decision.action,
                    params=tuple(sorted(decision.params.items())),
                    valid=True,
                    fallback=fallback,
                    event=event,
                ))

        self.state = update_faction_status(self.state)
        return self.state

    def run(self, turns: int) -> GameState:
        for _ in range(turns):
            active = sum(
                1 for f in self.state.factions.values() if f.is_active
            )
            if active <= 1:
                break  # game decided: at most one faction remains
            self.step()
        return self.state


# -- per-turn helpers --------------------------------------------------------

GOLD_INCOME_DIV = 3


def apply_income(state: GameState, rng: random.Random) -> GameState:
    """Turn-start income and upkeep, in fixed city_id order.

    Each city rolls two uniforms (gold first, then food):
      gold += int(commerce // 5 * rg)
      food += int(agriculture // 4 * rf)
    Then upkeep: food -= troops // 10. If food goes negative it is clamped to
    0 and the garrison deserts by 10% (troops = troops * 9 // 10).
    """
    new_cities = {}
    for cid in sorted(state.cities):
        c = state.cities[cid]
        rg = rng.uniform(0.8, 1.2)
        rf = rng.uniform(0.8, 1.2)
        gold = c.gold + int(c.commerce // GOLD_INCOME_DIV * rg)
        food = c.food + int(c.agriculture // 4 * rf)
        food -= c.troops // 10
        troops = c.troops
        if food < 0:
            food = 0
            troops = c.troops * 9 // 10
        new_cities[cid] = replace(c, gold=gold, food=food, troops=troops)
    return replace(state, cities=new_cities)


def update_faction_status(state: GameState) -> GameState:
    """Deactivate any faction that no longer owns a city."""
    new_factions = {}
    for fid, f in state.factions.items():
        has_cities = any(c.owner == fid for c in state.cities.values())
        new_factions[fid] = replace(f, is_active=has_cities)
    return replace(state, factions=new_factions)


def compute_winner(state: GameState) -> str | None:
    """Faction with the lexicographically largest ``(cities, total_troops)``.

    Returns ``None`` only when the leading factions are exactly tied on both
    city count and total troops.
    """
    scores: dict[str, tuple[int, int]] = {}
    for fid in state.factions:
        owned = [c for c in state.cities.values() if c.owner == fid]
        scores[fid] = (len(owned), sum(c.troops for c in owned))
    best = max(scores.values())
    winners = [fid for fid, s in scores.items() if s == best]
    return winners[0] if len(winners) == 1 else None
