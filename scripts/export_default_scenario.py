#!/usr/bin/env python3
"""Export the built-in 9-city scenario to scenario format v1 (data/scenarios/default_v1.json).
The unit test tests/test_scenario.py checks that loading it reproduces build_initial_state('default') exactly."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from slg.engine.initial_state import build_initial_state  # noqa: E402
from slg.web.payload import CITY_POS  # noqa: E402

st = build_initial_state("default")
edges = sorted({tuple(sorted((a, b))) for a, nb in st.adjacency.items() for b in nb})
caps = {"faction_1": "xuchang", "faction_2": "luoyang", "faction_3": "jianye"}
doc = {
    "format": 1,
    "id": "default_v1",
    "name_zh": "三足鼎立(內建 9 城)",
    "year": 208,
    "summary_zh": "曹操、劉備、孫權三方各據三城的內建開局。",
    "verification": "game_design",  # a balanced game scenario, not a historical claim
    "sources": [],
    "rules": None,
    "map": {
        "cities": [{"id": cid, "name_zh": c.name, "pos": list(CITY_POS[cid])} for cid, c in st.cities.items()],
        "edges": [list(e) for e in edges],
    },
    "factions": [{"id": f.faction_id, "name_zh": f.name, "capital": caps[f.faction_id], "playable": True}
                 for f in st.factions.values()],
    "cities": [{"id": c.city_id, "owner": c.owner, "agriculture": c.agriculture, "commerce": c.commerce,
                "defense": c.defense, "gold": c.gold, "food": c.food, "troops": c.troops} for c in st.cities.values()],
    "officers": [{"id": o.officer_id, "name_zh": o.name, "faction": o.faction_id, "city": o.city_id,
                  "politics": o.politics, "war": o.war, "leadership": o.leadership, "loyalty": o.loyalty,
                  "ambition": o.ambition} for o in st.officers.values()],
    "events": [],
    "victory": {"type": "most_cities", "turns": 30},
}
out = ROOT / "data" / "scenarios" / "default_v1.json"
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("wrote", out, len(doc["officers"]), "officers")
