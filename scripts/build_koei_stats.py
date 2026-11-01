#!/usr/bin/env python3
"""Normalise the fan-compiled Koei stats sheet (tab 三國武將) into data/sanguo/koei_stats.json.

Input : data/sanguo/raw_sheet/csv/03_三國武將.csv  (made by scripts/xlsx_to_csv.py from the sheet's xlsx export)
Output: data/sanguo/koei_stats.json
  {"source": ..., "games": [1..14], "officers": [{name, courtesy, sex, father, mother, spouse, bio,
                                                   stats: {"11": {"統率": 95, ...}, ...},
                                                   mean: {"統率": .., "武力": .., ...},   # over games 4-14
                                                   n_games: int}]}
Also reports how many of our 186 database officers (data/sanguo/officers_*.json) are found by name.
The data is NOT used by the engine; it is reference material for later calibration.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/sanguo/raw_sheet/csv/03_三國武將.csv"
OUT = ROOT / "data/sanguo/koei_stats.json"
STAT_FIX = {"统率": "統率", "體力": "體力"}
MEAN_GAMES = range(4, 15)  # games with the comparable 統率/武力/智力/政治(/魅力) set
CORE = ("統率", "武力", "智力", "政治", "魅力")
META = {"字": "courtesy", "性別": "sex", "父親": "father", "母親": "mother", "配偶": "spouse", "武將列傳": "bio"}


def num(v):
    try:
        return float(v)
    except ValueError:
        return None


def main():
    rows = list(csv.reader(open(SRC, encoding="utf-8")))
    header = [h.replace("\n", "").strip() for h in rows[0]]
    cols = []  # (index, game, stat) or (index, None, metakey)
    for i, h in enumerate(header[1:], 1):
        m = re.match(r"(\d+)代(.+)", h)
        if m:
            cols.append((i, int(m.group(1)), STAT_FIX.get(m.group(2), m.group(2))))
        elif h in META:
            cols.append((i, None, META[h]))
    officers = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        o = {"name": row[0].strip(), "stats": {}}
        for i, game, key in cols:
            v = row[i].strip() if i < len(row) else ""
            if not v:
                continue
            if game is None:
                o[key] = v
            elif (n := num(v)) is not None:
                o["stats"].setdefault(str(game), {})[key] = int(n) if n == int(n) else n
        mean = {}
        for s in CORE:
            vals = [g[s] for k, g in o["stats"].items() if int(k) in MEAN_GAMES and s in g]
            if vals:
                mean[s] = round(sum(vals) / len(vals), 1)
        o["mean"] = mean
        o["n_games"] = len(o["stats"])
        officers.append(o)
    json.dump({"source": "Google Sheet「三國志1-14全武將」(fan-compiled; credits: cws0324, Alexchan@HKSAN; 14代 added 2026-07-18). "
                         "Unverified; reference only, not used by the engine.",
               "games": list(range(1, 15)), "mean_games": [4, 14], "officers": officers},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    byname = {}
    for o in officers:
        byname.setdefault(o["name"], []).append(o)
    ours = [x for f in ("wei", "shu", "wu", "others") for x in json.load(open(ROOT / f"data/sanguo/officers_{f}.json"))]
    hit = [x for x in ours if x["name"] in byname]
    dup = [x["name"] for x in hit if len(byname[x["name"]]) > 1]
    print(f"{len(officers)} officers in sheet; {len(hit)}/{len(ours)} database officers matched by name; duplicated names among matches: {dup}")
    print("missing:", [x["name"] for x in ours if x["name"] not in byname])


if __name__ == "__main__":
    main()
