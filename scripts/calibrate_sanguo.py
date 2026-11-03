#!/usr/bin/env python3
"""Calibrate data/sanguo officer stats against the fan-compiled Koei table, and list expansion candidates.

Reads  data/sanguo/koei_stats.json (scripts/build_koei_stats.py) and data/sanguo/officers_*.json.
Writes (in place) to each officer record, leaving the original `stats_estimate` untouched:
  stats_koei        mean over Koei games 4-14 for leadership/war/intellect/politics/charm (null if the sheet has none)
  koei_name         the sheet row used (name variants / same-name splits are resolved by ALIAS)
  koei_n_games      how many games the row appears in
  stats_calibrated  = stats_koei rounded when the row appears in >= MIN_GAMES games, otherwise = stats_estimate
  calibration       "koei_mean" | "estimate_kept" ; plus "disputed": [...] when |estimate - koei| >= DISPUTE for a stat
Also writes data/sanguo/candidates_officers.json: sheet officers NOT in our database, ranked by appearances and strength,
with Koei-mean initial stats (faction / home city are unknown and left null for later classification), and prints a
report on how the 42 in-game officers' engine stats differ from the calibrated ones (engine untouched).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data/sanguo"
MIN_GAMES = 3
DISPUTE = 25
TOP_CANDIDATES = 200
ALIAS = {"陳羣": "陳群", "楊修": "楊脩", "麋竺": "糜竺", "麋芳": "糜芳", "馬忠": "馬忠(蜀)"}
M = {"leadership": "統率", "war": "武力", "intellect": "智力", "politics": "政治", "charm": "魅力"}


def main():
    sheet = {o["name"]: o for o in json.load(open(D / "koei_stats.json"))["officers"]}
    used = set()
    counts = {"koei_mean": 0, "estimate_kept": 0}
    disputed_total = 0
    files = {f: json.load(open(D / f"officers_{f}.json")) for f in ("wei", "shu", "wu", "others")}
    calibrated = {}
    for f, lst in files.items():
        for x in lst:
            row = sheet.get(x["name"]) or sheet.get(ALIAS.get(x["name"], ""))
            est = x["stats_estimate"]
            if row:
                used.add(row["name"])
                x["koei_name"] = row["name"]
                x["koei_n_games"] = row["n_games"]
                x["stats_koei"] = {k: row["mean"].get(c) for k, c in M.items()}
            else:
                x["koei_name"], x["koei_n_games"], x["stats_koei"] = None, 0, None
            if row and row["n_games"] >= MIN_GAMES:
                cal = {}
                for k, c in M.items():
                    cal[k] = round(row["mean"][c]) if c in row["mean"] else est.get(k)
                x["stats_calibrated"] = {k: v for k, v in cal.items() if v is not None}
                x["calibration"] = "koei_mean"
                dis = [k for k in est if est[k] is not None and row["mean"].get(M.get(k, ""), None) is not None
                       and abs(est[k] - row["mean"][M[k]]) >= DISPUTE]
                if dis:
                    x["disputed"] = dis
                    disputed_total += len(dis)
                else:
                    x.pop("disputed", None)
            else:
                x["stats_calibrated"] = {k: v for k, v in est.items() if v is not None}
                x["calibration"] = "estimate_kept"
                x.pop("disputed", None)
            counts[x["calibration"]] += 1
            calibrated[x["id"]] = x
        json.dump(lst, open(D / f"officers_{f}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("calibration:", counts, "disputed stat entries:", disputed_total)

    cands = []
    for name, o in sheet.items():
        if name in used or o["n_games"] < 6 or not o["mean"] or max(o["mean"].values()) > 100:
            continue  # the sheet also has summary rows (e.g. 每代武將數) whose values exceed 100
        m = o["mean"]
        cands.append({
            "name": name, "courtesy": o.get("courtesy"), "sex": o.get("sex"), "bio": o.get("bio"),
            "koei_n_games": o["n_games"],
            "stats_calibrated": {k: round(m[c]) for k, c in M.items() if c in m},
            "score": round(sum(m.values()) / len(m), 1),
            "faction": None, "home_city": None, "verification": "unverified",
        })
    cands.sort(key=lambda c: (-c["koei_n_games"], -c["score"]))
    json.dump(cands[:TOP_CANDIDATES], open(D / "candidates_officers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"candidates: {len(cands)} with >=6 games and not in the database; wrote top {min(TOP_CANDIDATES, len(cands))}")

    # engine comparison (engine untouched)
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from slg.engine.initial_state import build_initial_state
    st = build_initial_state("default")
    rows = []
    for o in st.officers.values():
        c = calibrated.get(o.officer_id, {}).get("stats_calibrated")
        if not c:
            continue
        rows.append((o.name, o.war - c["war"], o.leadership - c["leadership"], o.politics - c["politics"]))
    n = len(rows)
    for i, lab in ((1, "war"), (2, "leadership"), (3, "politics")):
        vals = [r[i] for r in rows]
        print(f"engine - calibrated {lab}: mean {sum(vals)/n:+.1f}, mean abs {sum(abs(v) for v in vals)/n:.1f}")
    rows.sort(key=lambda r: -max(abs(r[1]), abs(r[2]), abs(r[3])))
    print("largest gaps (name, war, leadership, politics):", [(r[0], round(r[1]), round(r[2]), round(r[3])) for r in rows[:8]])


if __name__ == "__main__":
    main()
