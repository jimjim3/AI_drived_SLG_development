"""One web game: a background thread runs the engine; the human faction is a blocking FactionAgent."""

from __future__ import annotations

import random
import threading

from ..agents.base import FactionAgent
from ..engine.game import Game, compute_winner
from ..engine.initial_state import build_initial_state
from ..engine.resolution import estimate_siege_ratio
from ..schema import AgentDecision, CAST_LIMIT, FactionPlan
from .backends import make_ai_agent
from .payload import state_payload


class PlanError(ValueError):
    pass


def parse_plan(data: dict) -> FactionPlan:
    """Structural parsing only; legality is judged by the engine, exactly as for AI plans."""
    if not isinstance(data, dict):
        raise PlanError("plan must be an object")
    orders = []
    for o in data.get("orders", []):
        if not isinstance(o, dict) or not isinstance(o.get("officer"), str) or not isinstance(o.get("action"), str):
            raise PlanError("each order needs string 'officer' and 'action'")
        params = o.get("params") or {}
        if not isinstance(params, dict):
            raise PlanError("params must be an object")
        orders.append(AgentDecision(o["officer"], o["action"], params))
    nxt = data.get("next_cast", [])
    if not isinstance(nxt, list) or not all(isinstance(x, str) for x in nxt):
        raise PlanError("next_cast must be a list of ids")
    if len(nxt) > CAST_LIMIT:
        raise PlanError(f"next_cast exceeds {CAST_LIMIT}")
    return FactionPlan(orders=tuple(orders), chronicle=str(data.get("chronicle", ""))[:2000], next_cast=tuple(nxt))


class HumanFactionAgent(FactionAgent):
    name = "human"

    def __init__(self, session: "Session", timeout: float = 900.0):
        self.session = session
        self.timeout = timeout
        self._plan: FactionPlan | None = None
        self._ev = threading.Event()

    def decide(self, view) -> FactionPlan:
        s = self.session
        with s.lock:
            s.view = view
            s.payload = state_payload(s.game.state, view)
            s.phase = "awaiting_input"
            self._plan = None
            self._ev.clear()
        got = self._ev.wait(self.timeout)
        with s.lock:
            s.phase = "resolving"
            plan = self._plan if got and self._plan is not None else FactionPlan()
            if not got:
                s.timeouts += 1
        return plan

    def submit(self, plan: FactionPlan) -> None:
        self._plan = plan
        self._ev.set()


class Session:
    def __init__(self, scenario="default", seed=0, player_faction="faction_2", turns=20, human_timeout=900.0, ai=None):
        self.lock = threading.RLock()
        self.turns = turns
        self.player_faction = player_faction
        self.phase = "starting"
        self.view = None
        self.payload = None
        self.timeouts = 0
        self.winner = None
        self.error = None
        state = build_initial_state(scenario=scenario)
        if player_faction not in state.factions:
            raise ValueError(f"unknown faction {player_faction!r}")
        self.human = HumanFactionAgent(self, human_timeout)
        ai = ai or {}
        agents = {f: make_ai_agent(ai.get(f, "rule")) for f in sorted(state.factions) if f != player_faction}
        agents[player_faction] = self.human
        self.game = Game(state, agents, random.Random(seed))
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            for _ in range(self.turns):
                if not self.game.state.cities_of(self.player_faction):
                    break
                self.game.step()
            with self.lock:
                self.winner = compute_winner(self.game.state)
                self.phase = "game_over"
        except Exception as exc:  # surfaced to the client instead of dying silently
            with self.lock:
                self.error = repr(exc)
                self.phase = "game_over"

    # --- API surface -------------------------------------------------
    def status(self) -> dict:
        with self.lock:
            v = self.view if self.phase == "awaiting_input" else None
            return {"phase": self.phase, "turn": self.game.state.turn, "events": list(v.events) if v else [],
                    "feedback": list(v.feedback) if v else [], "winner": self.winner, "error": self.error,
                    "timeouts": self.timeouts}

    def state(self) -> dict | None:
        with self.lock:
            return self.payload if self.phase == "awaiting_input" else None

    def submit_plan(self, data: dict) -> None:
        with self.lock:
            if self.phase != "awaiting_input":
                raise PlanError("not awaiting input")
        self.human.submit(parse_plan(data))

    def estimate(self, city: str, target: str, troops: int) -> float:
        """Same scouting estimate an AI sees; only for officers in the current cast, visible targets."""
        with self.lock:
            if self.phase != "awaiting_input":
                raise PlanError("not awaiting input")
            st = self.game.state
            visible = {f["id"] for f in self.view.frontier}
            if target not in visible:
                raise PlanError("target not visible")
            cands = [o for o in self.view.cast if o["city"] == city]
            if not cands:
                raise PlanError("no cast officer in that city")
            return float(estimate_siege_ratio(st, st.officers[cands[0]["id"]], target, int(troops)))
