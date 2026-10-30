"""Tunable siege-strength rules.

``v2`` is the shipped rule set and the default, so existing evaluations, logs and replays are unchanged.
Other sets are *experimental*: they exist to test whether attacking can become a reasonable option
(docs/EVALUATION.md section 13) and are NOT recorded in a TurnLog, so a game played under one cannot be
replayed unless the same set is selected again (``set_rules``).

  defender strength = garrison * (1 + defense / defense_divisor) * (dq_base + best_defender_skill / dq_div)
  attacker strength = troops   * (0.5 + (war + leadership) / 200)               (unchanged in all sets)
  pooling           = a siege may also draw ``pool_factor`` of the spare troops of each friendly city within
                      ``pool_depth`` hops over friendly cities (spare = troops above the minimum garrison);
                      factor 0 means origin city only (shipped rule). Depth 1 favours a faction whose front city
                      is a hub (Cao's Xuchang has two friendly neighbours, Liu's and Sun's front cities have one);
                      depth 2 lets every faction gather all three of its cities.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from ..schema import SIEGE_MIN_GARRISON, GameState


@dataclass(frozen=True)
class CombatRules:
    name: str
    defense_divisor: float = 200.0
    dq_base: float = 0.5
    dq_div: float = 100.0
    pool_factor: float = 0.0
    pool_depth: int = 1  # how many friendly-city hops away troops can be drawn from
    far_march_factor: float = 1.0  # attacker strength multiplier on a far (long-march) edge; 1.0 = distance ignored
    city_caps: bool = False  # per-city development / population ceilings (CITY_CAPS); off = unlimited, as shipped
    cap_tiers: bool | str = False  # with city_caps: use Koei size tiers (True for KOEI_TIER_CAPS, "flat" for KOEI_FLAT_TIER_CAPS)
    march_food_rate: float = 0.0  # a siege eats troops * km / 1000 * rate food at launch; 0 = free, as shipped


RULESETS: dict[str, CombatRules] = {
    "v2": CombatRules("v2"),
    # lighter walls and a weaker defender-skill bonus
    "soft": CombatRules("soft", defense_divisor=300.0, dq_base=0.65, dq_div=150.0),
    "softer": CombatRules("softer", defense_divisor=400.0, dq_base=0.75, dq_div=200.0),
    "softest": CombatRules("softest", defense_divisor=600.0, dq_base=0.85, dq_div=300.0),
    # troop concentration, alone and combined with the lighter defender bonuses
    "pool": CombatRules("pool", pool_factor=0.5),
    "soft_pool": CombatRules("soft_pool", defense_divisor=300.0, dq_base=0.65, dq_div=150.0, pool_factor=0.5),
    "softer_pool": CombatRules("softer_pool", defense_divisor=400.0, dq_base=0.75, dq_div=200.0, pool_factor=0.5),
    # symmetric versions: every faction can gather its whole realm at the front
    "pool2": CombatRules("pool2", pool_factor=0.5, pool_depth=2),
    "soft_pool2": CombatRules("soft_pool2", defense_divisor=300.0, dq_base=0.65, dq_div=150.0, pool_factor=0.5, pool_depth=2),
    "softer_pool2": CombatRules("softer_pool2", defense_divisor=400.0, dq_base=0.75, dq_div=200.0, pool_factor=0.5, pool_depth=2),
    # distance matters: a siege over a far edge (see FAR_EDGES) is weakened by marching attrition
    "softer_pool2_far": CombatRules("softer_pool2_far", defense_divisor=400.0, dq_base=0.75, dq_div=200.0,
                                    pool_factor=0.5, pool_depth=2, far_march_factor=0.75),
    # economy: city size/population ceilings and a food bill that grows with march distance (no strength penalty)
    "softer_pool2_econ": CombatRules("softer_pool2_econ", defense_divisor=400.0, dq_base=0.75, dq_div=200.0,
                                     pool_factor=0.5, pool_depth=2, city_caps=True, march_food_rate=1.0),
    # same economy, but city sizes follow Koei's Sangokushi 11 tiers (agy-reported, unverified)
    "softer_pool2_econ2": CombatRules("softer_pool2_econ2", defense_divisor=400.0, dq_base=0.75, dq_div=200.0,
                                      pool_factor=0.5, pool_depth=2, city_caps=True, cap_tiers=True, march_food_rate=1.0),
    # tuned economy (docs/EVALUATION.md §21.2): march_food_rate=0.5 keeps Sun active while preventing edge dominance
    "softer_pool2_econ3": CombatRules("softer_pool2_econ3", defense_divisor=400.0, dq_base=0.75, dq_div=200.0,
                                      pool_factor=0.5, pool_depth=2, city_caps=True, cap_tiers=True, march_food_rate=0.5),
}

# Real great-circle distances in km between neighbouring cities (from agy-reported coordinates in
# data/sanguo/maps/geo_agy.json; unverified). Edges of 500 km or more count as "far": the route crosses mountains
# or a great river and takes more than a season.
EDGE_KM: dict[frozenset, int] = {
    frozenset(("chenliu", "xuchang")): 102,
    frozenset(("xuchang", "luoyang")): 144,
    frozenset(("xuchang", "xiangyang")): 276,
    frozenset(("luoyang", "xiangyang")): 292,
    frozenset(("luoyang", "wancheng")): 180,
    frozenset(("xiangyang", "jianye")): 628,
    frozenset(("jianye", "wujun")): 192,
    frozenset(("wancheng", "hanzhong")): 513,
    frozenset(("wujun", "kuaiji")): 146,
    frozenset(("wujun", "xiangyang")): 800,  # only exists in the +sun2 experiment
}
FAR_KM = 500
DEFAULT_KM = 250

# City size: (agriculture cap, commerce cap, troop cap = population). Only used when rules.city_caps is on.
# Caps sit well above the starting values, so they bite only after sustained development / recruiting.
CITY_CAPS: dict[str, tuple[int, int, int]] = {
    "xuchang": (900, 900, 2400), "luoyang": (900, 900, 2200), "jianye": (800, 800, 2000),
    "xiangyang": (750, 750, 1800), "chenliu": (700, 700, 1600), "wancheng": (700, 700, 1600),
    "wujun": (650, 650, 1500), "hanzhong": (600, 600, 1400), "kuaiji": (550, 550, 1100),
}
# Koei Sangokushi 11 city sizes as reported by agy (data/sanguo/koei_city_sizes_agy.json; unverified), mapped to caps.
KOEI_SIZE = {"luoyang": "xl", "xuchang": "l", "xiangyang": "l", "jianye": "l",
             "chenliu": "m", "wancheng": "m", "wujun": "m", "hanzhong": "m", "kuaiji": "s"}
KOEI_TIER_CAPS = {"xl": (900, 900, 2400), "l": (800, 800, 2000), "m": (700, 700, 1600), "s": (550, 550, 1100)}
# Flattened version: tier gaps halved (50, 50, 75 for agri/comm; 200, 200, 250 for troops)
KOEI_FLAT_TIER_CAPS = {"xl": (900, 900, 2400), "l": (850, 850, 2200), "m": (800, 800, 2000), "s": (725, 725, 1750)}
UNCAPPED = 10 ** 9


def edge_km(a: str, b: str) -> int:
    return EDGE_KM.get(frozenset((a, b)), DEFAULT_KM)


def city_caps(city_id: str) -> tuple[int, int, int]:
    rules = active()
    if not rules.city_caps:
        return (UNCAPPED,) * 3
    if rules.cap_tiers == "flat":
        return KOEI_FLAT_TIER_CAPS.get(KOEI_SIZE.get(city_id, ""), (UNCAPPED,) * 3)
    if isinstance(rules.cap_tiers, dict):
        return rules.cap_tiers.get(KOEI_SIZE.get(city_id, ""), (UNCAPPED,) * 3)
    if rules.cap_tiers:
        return KOEI_TIER_CAPS.get(KOEI_SIZE.get(city_id, ""), (UNCAPPED,) * 3)
    return CITY_CAPS.get(city_id, (UNCAPPED,) * 3)


def march_food(origin_id: str, target_id: str, troops: int) -> int:
    """Food a siege of ``troops`` eats on the way (0 under the shipped rules)."""
    rate = active().march_food_rate
    return int(troops * edge_km(origin_id, target_id) / 1000 * rate) if rate > 0 else 0


def far_march_factor(origin_id: str, target_id: str) -> float:
    return active().far_march_factor if edge_km(origin_id, target_id) >= FAR_KM else 1.0


_active: CombatRules = RULESETS["v2"]


def active() -> CombatRules:
    return _active


def set_rules(name: str) -> CombatRules:
    global _active
    try:
        _active = RULESETS[name]
    except KeyError:
        raise ValueError(f"unknown combat rules {name!r}; choose from {sorted(RULESETS)}") from None
    return _active


@contextmanager
def use_rules(name: str):
    previous = _active.name
    set_rules(name)
    try:
        yield _active
    finally:
        set_rules(previous)


def _spare(city) -> int:
    return max(0, city.troops - SIEGE_MIN_GARRISON)


def _pool_sources(state: GameState, origin_id: str) -> list:
    """Friendly cities within ``pool_depth`` hops over friendly cities, nearest first (ties by id)."""
    owner = state.city(origin_id).owner
    seen = {origin_id}
    frontier = [origin_id]
    out: list = []
    for _ in range(max(1, active().pool_depth)):
        nxt = sorted({cid for cur in frontier for cid in state.adjacency[cur]
                      if cid not in seen and state.city(cid).owner == owner})
        for cid in nxt:
            seen.add(cid)
            out.append(state.city(cid))
        frontier = nxt
    return out


def siege_capacity(state: GameState, origin) -> int:
    """Most troops a siege launched from ``origin`` may field (before rounding to the troop step)."""
    total = _spare(origin)
    factor = active().pool_factor
    if factor > 0:
        total += sum(int(_spare(c) * factor) for c in _pool_sources(state, origin.city_id))
    return total


def siege_contributions(state: GameState, origin, troops: int) -> list[tuple[str, int]]:
    """Which cities supply ``troops`` for a siege from ``origin``: the origin first, then pooled neighbours."""
    own = min(troops, _spare(origin))
    parts = [(origin.city_id, own)]
    remaining = troops - own
    factor = active().pool_factor
    if remaining > 0 and factor > 0:
        for c in _pool_sources(state, origin.city_id):
            take = min(remaining, int(_spare(c) * factor))
            if take > 0:
                parts.append((c.city_id, take))
                remaining -= take
    if remaining > 0:  # cannot happen for a validated order; keep the books balanced regardless
        parts[0] = (origin.city_id, parts[0][1] + remaining)
    return parts
