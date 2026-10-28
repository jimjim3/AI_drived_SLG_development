"""Story text (zh-TW) for scenarios, lords, cities, officers and events.

Pure data + lookup helpers. Nothing here touches game rules or RNG, so the engine
stays the single source of truth; the UI/agents may call these for presentation.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data"
SEASONS = ("春", "夏", "秋", "冬")
TURNS_PER_SEASON = 1  # presentation only: one turn = one season, four turns = one year
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@lru_cache(maxsize=None)
def load_narrative(lang: str = "zh-TW") -> dict:
    folder = _DATA / lang.replace("-", "_")
    if not folder.is_dir():
        raise ValueError(f"No narrative data for language {lang!r}")
    out = {}
    for name in ("world", "officers", "events", "openings", "transitions"):
        out[name] = json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))
    return out


def opening(scenario: str, faction_id: str, lang: str = "zh-TW") -> dict:
    """Opening briefing for the chosen scenario AND lord (headline, situation, advice, tone)."""
    kind = scenario.split(":", 1)[0]  # "advantage:faction_1" -> "advantage"; the openings are written per lord
    key = f"{kind}.{faction_id}"
    try:
        return load_narrative(lang)["openings"][key]
    except KeyError:
        raise KeyError(f"No opening for scenario/lord {key!r}") from None


def lord(faction_id: str, lang: str = "zh-TW") -> dict:
    return load_narrative(lang)["world"]["lords"][faction_id]


def city(city_id: str, lang: str = "zh-TW") -> dict:
    return load_narrative(lang)["world"]["cities"][city_id]


def officer(officer_id: str, lang: str = "zh-TW") -> dict:
    return load_narrative(lang)["officers"][officer_id]


def scenario(scenario_id: str, lang: str = "zh-TW") -> dict:
    return load_narrative(lang)["world"]["scenarios"][scenario_id]


def calendar_label(turn: int, lang: str = "zh-TW") -> dict:
    """Year/season label for a 0-based turn number (presentation only)."""
    if turn < 0:
        raise ValueError("turn must be >= 0")
    season = SEASONS[(turn // TURNS_PER_SEASON) % 4]
    year = turn // (TURNS_PER_SEASON * 4) + 1
    flavor = load_narrative(lang)["world"]["calendar"]["season_flavor"][season]
    return {"year": year, "season": season, "label": f"第{year}年{season}", "flavor": flavor}


def render_event(key: str, variant: int = 0, lang: str = "zh-TW", **fields) -> str:
    """Fill an event template. `variant` is any int (e.g. turn number); it is taken modulo the
    number of variants, so the result is deterministic and the caller owns the choice."""
    templates = load_narrative(lang)["events"][key]
    text = templates[variant % len(templates)]
    needed = set(_PLACEHOLDER.findall(text))
    missing = needed - set(fields)
    if missing:
        raise KeyError(f"Event {key!r} needs fields {sorted(missing)}")
    return _PLACEHOLDER.sub(lambda m: str(fields[m.group(1)]), text)


def transition(key: str, variant: int = 0, season: str | None = None, lang: str = "zh-TW") -> str:
    """Scene-change flavour text (season change, new year, march, quiet turn...). `variant` picks deterministically."""
    pool = load_narrative(lang)["transitions"][key]
    if isinstance(pool, dict):
        pool = pool[season]
    return pool[variant % len(pool)]
