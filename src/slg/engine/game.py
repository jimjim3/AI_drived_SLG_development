"""Game orchestration: decide, apply, step, run.

The :class:`Game` owns the mutable simulation handle. The state itself is an
immutable :class:`GameState` that is replaced (copy-on-write) on every action.
A deterministic, sequential order (factions by id, officers by id) plus a
seeded RNG make a full run reproducible.
"""

from __future__ import annotations

import random
from dataclasses import replace

from ..agents.base import Agent, FactionAgent
from ..agents.rule_based import RuleBasedAgent
from ..schema import (
    CAST_LIMIT,
    DEFECT_BELOW,
    DEFECT_REJOIN_LOYALTY,
    DISOBEY_BELOW,
    EVENT_LIMIT,
    LOYALTY_BOOST,
    LOYALTY_MAX,
    NEGLECT_PENALTY_START,
    AgentDecision,
    FactionPlan,
    FactionTurnLog,
    GameState,
    LogEntry,
    ResolutionEvent,
)
from .legal_actions import generate_legal_actions
from .resolution import resolve_decision
from .validation import validate_decision
from .view import build_faction_view, forced_cast, select_cast


class Game:
    def __init__(
        self,
        state: GameState,
        agents_by_faction,
        rng: random.Random,
        delegate_agent: Agent | None = None,
    ):
        self.state = state
        self.agents = agents_by_faction
        self.rng = rng
        self.delegate_agent = (
            delegate_agent if delegate_agent is not None else RuleBasedAgent("balanced")
        )
        self.next_cast: dict[str, tuple] = {}
        self.feedback: dict[str, tuple] = {}
        self.faction_logs: list[FactionTurnLog] = []
        self.stats = {
            "decisions": 0,
            "valid": 0,
            "rejected": 0,
            "fallbacks": 0,
            "orders": 0,
            "orders_rejected": 0,
            "delegated": 0,
            "plan_failures": 0,
            "disobeyed": 0,
        }
        self.events: list = []
        self.incidents: list[ResolutionEvent] = []
        self.log_entries: list = []
        self._fallback = RuleBasedAgent()

    def _is_faction_level(self, fid: str) -> bool:
        agent = self.agents.get(fid)
        if agent is None:
            return False
        if getattr(agent, "name", "") == "replay" and hasattr(agent, "is_faction_level"):
            return agent.is_faction_level(fid)
        return isinstance(agent, FactionAgent)

    # -- decision with safety net -----------------------------------------
    def decide(self, officer, agent: Agent | None = None) -> tuple[AgentDecision, bool, str, int]:
        """Return ``(decision, fallback, agent_name, legal_count)``.

        Safety net: try the primary agent up to twice; on exception or
        validation failure record a rejection. After two primary failures fall
        back to the rule-based agent, and finally to a hardcoded ``rest``
        (always legal). This guarantees ``stats["valid"] == stats["decisions"]``.
        """
        self.stats["decisions"] += 1
        if agent is None:
            agent = self.agents.get(officer.faction_id)
        legal = generate_legal_actions(self.state, officer)
        legal_count = len(legal)
        agent_name = getattr(agent, "name", "agent") if agent is not None else "safety_net"

        # Primary agent: up to two attempts.
        if isinstance(agent, Agent) or (agent is not None and not isinstance(agent, FactionAgent)):
            for _ in range(2):
                try:
                    decision = agent.decide(self.state, officer, legal)
                except Exception:
                    if getattr(agent, "name", "") == "replay_delegate":
                        raise
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
        noticed_by_faction: dict[str, set[str]] = {fid: set() for fid in self.state.factions}

        for fid in order:
            faction = self.state.factions[fid]
            if not faction.is_active:
                continue
            if not self.state.cities_of(fid):
                continue  # eliminated mid-turn

            agent = self.agents.get(fid)
            if isinstance(agent, FactionAgent):
                # 1. build view
                prev_events = [e for e in self.events if e.turn == turn - 1] + [
                    inc for inc in self.incidents if inc.turn == turn - 1
                ]
                cast = select_cast(
                    self.state,
                    fid,
                    requested=self.next_cast.get(fid, ()),
                    forced=forced_cast(self.state, fid, prev_events),
                )
                view = build_faction_view(
                    self.state,
                    fid,
                    cast,
                    prev_events,
                    self.feedback.get(fid, ()),
                )

                # 2. plan
                plan_failed = False
                plan_error_str = None
                try:
                    plan = agent.decide(view)
                except Exception as exc:
                    if getattr(agent, "name", "") == "replay":
                        raise
                    self.stats["plan_failures"] += 1
                    plan = FactionPlan()
                    plan_failed = True
                    plan_error_str = str(exc)

                # 3. process orders
                acted_officers: set[str] = set()
                executed_decisions: list[AgentDecision] = []
                ordered_officers: list[str] = []
                rejected_list: list[tuple[str, str, str]] = []
                disobey_feedback: list[str] = []
                noticed_candidates: list[str] = []

                for order_decision in plan.orders:
                    oid = order_decision.officer_id
                    officer = self.state.officers.get(oid)
                    reason = None
                    if officer is None:
                        reason = f"officer {oid!r} not found"
                    elif officer.faction_id != fid:
                        reason = f"officer {oid!r} not in faction {fid!r}"
                    elif not officer.is_alive:
                        reason = f"officer {oid!r} not alive"
                    elif oid in acted_officers:
                        reason = f"officer {oid!r} already acted this turn"
                    else:
                        ok, val_reason = validate_decision(self.state, officer, order_decision)
                        if not ok:
                            reason = val_reason

                    if reason is not None:
                        self.stats["rejected"] += 1
                        self.stats["orders_rejected"] += 1
                        rejected_list.append((oid, order_decision.action, reason))
                    else:
                        acted_officers.add(oid)
                        ordered_officers.append(oid)
                        self.stats["decisions"] += 1
                        self.stats["valid"] += 1
                        self.stats["orders"] += 1
                        executed_decisions.append(order_decision)

                        disobeyed = False
                        if self._is_faction_level(fid) and officer.loyalty < DISOBEY_BELOW:
                            u = self.rng.random()
                            p = min(
                                0.5,
                                (DISOBEY_BELOW - officer.loyalty) / 100.0 * (0.5 + officer.ambition / 100.0),
                            )
                            if u < p:
                                disobeyed = True

                        if disobeyed:
                            self.stats["disobeyed"] += 1
                            disobey_feedback.append(f"{oid} 抗旨（忠誠{officer.loyalty}）")
                            rest_decision = AgentDecision(oid, "rest")
                            event = self.apply(officer, rest_decision)
                            event = replace(
                                event,
                                detail=f"抗旨: 忠誠{officer.loyalty} 野心{officer.ambition} 原令{order_decision.action}",
                            )
                            self.events[-1] = event
                            legal_count = len(generate_legal_actions(self.state, officer))
                            self.log_entries.append(
                                LogEntry(
                                    turn=turn,
                                    officer_id=officer.officer_id,
                                    faction_id=officer.faction_id,
                                    agent_name=getattr(agent, "name", "faction_agent"),
                                    legal_count=legal_count,
                                    action="rest",
                                    params=(),
                                    valid=True,
                                    fallback=False,
                                    event=event,
                                    source="disobey",
                                )
                            )
                        else:
                            legal_count = len(generate_legal_actions(self.state, officer))
                            event = self.apply(officer, order_decision)
                            self.log_entries.append(
                                LogEntry(
                                    turn=turn,
                                    officer_id=officer.officer_id,
                                    faction_id=officer.faction_id,
                                    agent_name=getattr(agent, "name", "faction_agent"),
                                    legal_count=legal_count,
                                    action=order_decision.action,
                                    params=tuple(sorted(order_decision.params.items())),
                                    valid=True,
                                    fallback=False,
                                    event=event,
                                    source="order",
                                )
                            )
                            if order_decision.action != "rest":
                                if oid not in noticed_candidates:
                                    noticed_candidates.append(oid)

                noticed_by_faction[fid] = set(noticed_candidates[:CAST_LIMIT])

                # 4. delegation
                delegated_officers: list[str] = []
                for oid in sorted(self.state.officers):
                    if oid in acted_officers:
                        continue
                    officer = self.state.officers.get(oid)
                    if officer is None or officer.faction_id != fid or not officer.is_alive:
                        continue
                    decision, fallback, _name, legal_count = self.decide(
                        officer, agent=self.delegate_agent
                    )
                    self.stats["delegated"] += 1
                    acted_officers.add(oid)
                    executed_decisions.append(decision)
                    delegated_officers.append(oid)
                    event = self.apply(officer, decision)
                    self.log_entries.append(
                        LogEntry(
                            turn=turn,
                            officer_id=officer.officer_id,
                            faction_id=officer.faction_id,
                            agent_name=getattr(self.delegate_agent, "name", "delegate"),
                            legal_count=legal_count,
                            action=decision.action,
                            params=tuple(sorted(decision.params.items())),
                            valid=True,
                            fallback=fallback,
                            event=event,
                            source="delegate",
                        )
                    )

                # 5. append FactionTurnLog and update next_cast / feedback
                self.faction_logs.append(
                    FactionTurnLog(
                        turn=turn,
                        faction_id=fid,
                        agent_name=getattr(agent, "name", "faction_agent"),
                        executed=tuple(executed_decisions),
                        chronicle=plan.chronicle,
                        next_cast=plan.next_cast,
                        rejected=tuple(rejected_list),
                        delegated=tuple(delegated_officers),
                        plan_failed=plan_failed,
                        ordered=tuple(ordered_officers),
                    )
                )
                self.next_cast[fid] = plan.next_cast
                feedback_items = [f"{o_id} {act}: {rsn}" for o_id, act, rsn in rejected_list]
                feedback_items.extend(disobey_feedback)
                if plan_failed and plan_error_str is not None:
                    feedback_items.append(f"plan failed: {plan_error_str}")
                self.feedback[fid] = tuple(feedback_items[:EVENT_LIMIT])

            else:
                executed_decisions = []
                for oid in sorted(self.state.officers):
                    officer = self.state.officers[oid]
                    if officer.faction_id != fid or not officer.is_alive:
                        continue
                    decision, fallback, agent_name, legal_count = self.decide(officer, agent=agent)
                    executed_decisions.append(decision)
                    event = self.apply(officer, decision)
                    self.log_entries.append(
                        LogEntry(
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
                            source="agent",
                        )
                    )
                self.faction_logs.append(
                    FactionTurnLog(
                        turn=turn,
                        faction_id=fid,
                        agent_name=getattr(agent, "name", "agent") if agent is not None else "agent",
                        executed=tuple(executed_decisions),
                    )
                )

        # Turn-end processing (before update_faction_status)
        # 3.a Neglect & loyalty boost/penalty for living officers of faction-level agents
        new_officers = dict(self.state.officers)
        for oid in sorted(new_officers):
            officer = new_officers[oid]
            if not officer.is_alive:
                continue
            if not self._is_faction_level(officer.faction_id):
                continue

            fid = officer.faction_id
            if oid in noticed_by_faction.get(fid, set()):
                new_neglect = 0
                new_loyalty = min(LOYALTY_MAX, officer.loyalty + LOYALTY_BOOST)
            else:
                new_neglect = officer.neglect + 1
                new_loyalty = officer.loyalty
                if new_neglect >= NEGLECT_PENALTY_START:
                    penalty = new_neglect - NEGLECT_PENALTY_START + 1
                    new_loyalty = max(0, new_loyalty - penalty)

            new_officers[oid] = replace(officer, neglect=new_neglect, loyalty=new_loyalty)

        self.state = replace(self.state, officers=new_officers)

        # 3.b Defection: all living officers sorted by officer_id
        new_officers = dict(self.state.officers)
        for oid in sorted(new_officers):
            officer = new_officers[oid]
            if not officer.is_alive:
                continue
            if officer.loyalty >= DEFECT_BELOW:
                continue

            # Always consume one random roll
            u = self.rng.random()

            # Adjacent enemy cities
            curr_city = officer.city_id
            adj_cids = self.state.adjacency.get(curr_city, ())
            enemy_cids = [
                cid for cid in adj_cids
                if self.state.city(cid).owner != officer.faction_id
            ]

            if enemy_cids:
                p = (officer.ambition / 100.0) * (1.0 - officer.loyalty / DEFECT_BELOW)
                if u < p:
                    target_cid = min(enemy_cids)
                    target_city = self.state.city(target_cid)
                    new_faction_id = target_city.owner
                    orig_faction_id = officer.faction_id

                    new_officers[oid] = replace(
                        officer,
                        faction_id=new_faction_id,
                        city_id=target_cid,
                        loyalty=DEFECT_REJOIN_LOYALTY,
                        neglect=0,
                    )
                    incident = ResolutionEvent(
                        turn=turn,
                        officer_id=oid,
                        faction_id=orig_faction_id,
                        action="defect",
                        city_id=target_cid,
                        detail=f"出奔: {orig_faction_id} -> {new_faction_id} (忠誠{officer.loyalty})",
                    )
                    self.incidents.append(incident)

        self.state = replace(self.state, officers=new_officers)

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
      gold += int(commerce // GOLD_INCOME_DIV * rg)
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
