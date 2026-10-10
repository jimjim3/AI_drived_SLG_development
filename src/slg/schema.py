"""Core data model for the SLG engine.

All state objects are frozen dataclasses. Mutations are expressed as
copy-on-write via ``dataclasses.replace`` so that the engine stays the single
source of truth and no agent can mutate state directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


# --- Tunable constants (M0a) -------------------------------------------------

DEVELOP_COST = 50          # gold cost for any develop_* action
GOLD_PER_TROOP = 1         # gold cost per recruited troop
MIN_RECRUIT = 100          # minimum troops a recruit action may request
MAX_RECRUIT = 1200         # hard cap on troops a single recruit may request
RECRUIT_STEP = 100         # granularity for recruit troop amounts
MIN_SIEGE_TROOPS = 500     # minimum troops to attempt a siege
SIEGE_MIN_TROOPS = MIN_SIEGE_TROOPS
SIEGE_TROOP_STEP = 100     # granularity for siege troop amounts
SIEGE_MIN_GARRISON = 100   # troops that must stay behind in the origin city

# Base increments for develop_* actions, scaled by the officer's politics.
DEVELOP_AGRICULTURE_BASE = 50
DEVELOP_COMMERCE_BASE = 50
DEVELOP_DEFENSE_BASE = 25


def develop_gain(base: int, politics: int) -> int:
    """Increment for a develop_* action performed by an officer.

    ``base * (50 + politics) // 100`` so that politics directly shapes the
    payoff of development.
    """
    return base * (50 + politics) // 100


@dataclass(frozen=True)
class ParamSpec:
    """Specification for one action parameter.

    Numeric parameters carry ``min``/``max``/``step``; discrete parameters
    (e.g. a destination city) carry ``choices``.
    """

    name: str
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple | None = None

    def is_discrete(self) -> bool:
        return self.choices is not None


@dataclass(frozen=True)
class LegalAction:
    """An action the engine has determined is currently executable.

    ``params`` maps a parameter name to its :class:`ParamSpec`. ``cost`` is
    informational only; the validator recomputes the real cost per action type.
    """

    action: str
    params: Mapping[str, ParamSpec] = field(default_factory=dict)
    cost: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class AgentDecision:
    """A concrete choice made by an agent for one officer.

    ``params`` maps a parameter name to a concrete value. ``memo`` is a short
    (<= 20 char) note the agent may attach.
    """

    officer_id: str
    action: str
    params: Mapping[str, object] = field(default_factory=dict)
    memo: str = ""


@dataclass(frozen=True)
class ResolutionEvent:
    """A single resolved action and its effect."""

    turn: int
    officer_id: str
    faction_id: str
    action: str
    city_id: str
    detail: str = ""
    captured_city: str | None = None
    captured_officers: tuple = ()


@dataclass(frozen=True)
class LogEntry:
    """One logged decision for a single officer in a single turn."""

    turn: int
    officer_id: str
    faction_id: str
    agent_name: str
    legal_count: int
    action: str
    params: tuple = ()
    valid: bool = True
    fallback: bool = False
    event: ResolutionEvent | None = None


@dataclass(frozen=True)
class TurnLog:
    """Complete log of one game run, suitable for deterministic replay."""

    seed: int
    turns: int
    entries: tuple = ()
    stats: tuple = ()


@dataclass(frozen=True)
class OfficerState:
    officer_id: str
    name: str
    faction_id: str
    city_id: str
    politics: int
    war: int
    leadership: int
    loyalty: int
    ambition: int
    is_alive: bool = True


@dataclass(frozen=True)
class CityState:
    city_id: str
    name: str
    owner: str
    agriculture: int
    commerce: int
    defense: int
    gold: int
    food: int
    troops: int


@dataclass(frozen=True)
class FactionState:
    faction_id: str
    name: str
    is_active: bool = True


@dataclass(frozen=True)
class GameState:
    turn: int
    factions: Mapping[str, FactionState]
    cities: Mapping[str, CityState]
    officers: Mapping[str, OfficerState]
    adjacency: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def adjacent(self, a: str, b: str) -> bool:
        """True if cities ``a`` and ``b`` are connected on the map."""
        return b in self.adjacency.get(a, ())

    def city(self, city_id: str) -> CityState:
        return self.cities[city_id]

    def officer(self, officer_id: str) -> OfficerState:
        return self.officers[officer_id]

    def faction(self, faction_id: str) -> FactionState:
        return self.factions[faction_id]

    def cities_of(self, faction_id: str) -> tuple[CityState, ...]:
        return tuple(c for c in self.cities.values() if c.owner == faction_id)

    def officers_of(self, faction_id: str) -> tuple[OfficerState, ...]:
        return tuple(o for o in self.officers.values() if o.faction_id == faction_id)

    def officers_in(self, city_id: str) -> tuple[OfficerState, ...]:
        return tuple(o for o in self.officers.values() if o.city_id == city_id)
