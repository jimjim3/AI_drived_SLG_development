"""Mechanical checks for data/sanguo/. Usage: python3 scripts/validate_sanguo_dataset.py [dir]  (exit 1 on errors)."""
import glob, json, pathlib, re, sys

ID = re.compile(r"^[a-z][a-z0-9_]*$")
STATS = ("leadership", "war", "intellect", "politics")


def validate(cities: list, officers: list) -> list[str]:
    errs = []
    cid = {}
    for c in cities:
        if not ID.match(str(c.get("id", ""))):
            errs.append(f"city bad id: {c.get('id')!r}")
        elif c["id"] in cid:
            errs.append(f"duplicate city id: {c['id']}")
        cid[c.get("id")] = c
        for k in ("x", "y"):
            if not isinstance(c.get(k), (int, float)) or isinstance(c.get(k), bool):
                errs.append(f"city {c.get('id')}: {k} not a number")
    for c in cities:
        for n in c.get("neighbors", []):
            if n == c["id"]:
                errs.append(f"city {c['id']}: lists itself as neighbor")
            elif n not in cid:
                errs.append(f"city {c['id']}: neighbor {n!r} does not exist")
            elif c["id"] not in cid[n].get("neighbors", []):
                errs.append(f"city {c['id']}-{n}: adjacency not symmetric")
    seen = {}
    for o in officers:
        oid = o.get("id")
        if not ID.match(str(oid)):
            errs.append(f"officer bad id: {oid!r}")
        elif oid in seen:
            errs.append(f"duplicate officer id: {oid} ({seen[oid]} and {o.get('name')})")
        seen[oid] = o.get("name")
        if o.get("home_city") not in cid:
            errs.append(f"officer {oid}: home_city {o.get('home_city')!r} not in cities")
        st = o.get("stats_estimate", {})
        for k in STATS:
            v = st.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 100:
                errs.append(f"officer {oid}: stats_estimate.{k}={v!r} not an int in 0..100")
        b, d = o.get("birth"), o.get("death")
        if isinstance(b, int) and isinstance(d, int) and d < b:
            errs.append(f"officer {oid}: death {d} before birth {b}")
        if not o.get("name"):
            errs.append(f"officer {oid}: missing name")
    return errs


def load(directory: pathlib.Path):
    cities = json.loads((directory / "cities.json").read_text(encoding="utf-8"))
    officers = []
    for f in sorted(glob.glob(str(directory / "officers_*.json"))):
        officers += json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
    return cities, officers


if __name__ == "__main__":
    d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1] / "data" / "sanguo")
    cities, officers = load(d)
    errs = validate(cities, officers)
    print(f"{len(cities)} cities, {len(officers)} officers, {len(errs)} problems")
    for e in errs[:80]:
        print(" -", e)
    sys.exit(1 if errs else 0)
