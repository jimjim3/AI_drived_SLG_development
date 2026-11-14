"""Save / resume for web games.

A save is a snapshot taken at the *start* of a turn (before any faction acts), so resuming simply re-runs that
turn: the restored RNG makes rule-based factions repeat themselves exactly, and the human is asked again.
LLM-controlled factions are asked again too (their answers may differ; that is expected).

The file is a pickle written and read only by this server from its own save directory, never from user uploads.
Names are validated by the caller (session ids match ``SID_RE``).
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path

VERSION = 1


def snapshot(game, meta: dict, steps_done: int) -> dict:
    return {
        "version": VERSION, "meta": meta, "steps_done": steps_done,
        "state": game.state, "rng": game.rng.getstate(), "next_cast": dict(game.next_cast),
        "feedback": dict(game.feedback), "stats": dict(game.stats), "events": list(game.events),
        "incidents": list(game.incidents), "faction_logs": list(game.faction_logs),
        "log_entries": list(game.log_entries),
    }


def restore(game, snap: dict) -> int:
    game.state = snap["state"]
    game.rng.setstate(snap["rng"])
    game.next_cast = dict(snap["next_cast"])
    game.feedback = dict(snap["feedback"])
    game.stats = dict(snap["stats"])
    game.events = list(snap["events"])
    game.incidents = list(snap["incidents"])
    game.faction_logs = list(snap["faction_logs"])
    game.log_entries = list(snap["log_entries"])
    return snap["steps_done"]


def write(path: Path, snap: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def read(path: Path) -> dict:
    with open(path, "rb") as f:
        snap = pickle.load(f)
    if not isinstance(snap, dict) or snap.get("version") != VERSION:
        raise ValueError("incompatible save file")
    return snap


def describe(path: Path) -> dict | None:
    """Small summary for the title screen, or None if there is no usable save."""
    try:
        snap = read(path)
    except Exception:
        return None
    m = snap["meta"]
    return {"turn": snap["state"].turn + 1, "scenario": m["scenario"], "player_faction": m["player_faction"],
            "rules": m["rules"], "turns": m["turns"]}
