"""Build the (unused-by-engine) Three Kingdoms dataset by asking agy in zero-tool `ask` mode.

Usage: python3 scripts/build_sanguo_dataset.py [cities|officers|all]
Outputs go to data/sanguo/. Only public history is sent; nothing from the repo is attached.
"""
import json, pathlib, re, subprocess, sys, glob, os

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sanguo"
COMPANION = os.environ.get("AGY_COMPANION") or glob.glob(os.path.expanduser("~/.claude/plugins/cache/agy-staff/agy/*/companion/agy-companion.mjs"))[0]

CITY_PROMPT = """請只輸出一份 JSON 陣列（不要 markdown 圍欄、不要解說），列出東漢末至三國時期最重要的 40 座城池／州郡治所，涵蓋魏、蜀、吳與群雄地盤（至少包含：洛陽 長安 許昌 鄴 陳留 宛 襄陽 江陵 成都 漢中 建業 吳郡 會稽 合肥 壽春 徐州(下邳) 北平 晉陽 武威 南鄭 永安 柴桑 廬江 長沙 零陵 交州治所 等）。
每個元素欄位：
{"id": "小寫拼音蛇形，如 luoyang", "name": "繁體中文城名", "region": "所屬州（如 司隸、兗州）", "x": 0到10的數字（東西，西小東大）, "y": 0到8的數字（南北，南小北大）, "terrain": ["平原"|"山地"|"關隘"|"臨江"|"臨海"|"盆地"...], "role": "一句話戰略定位（≤25字，只寫地理與軍事位置）", "neighbors": ["相鄰城池的 id，須在本列表內，且必須雙向（A 列 B，B 也必須列 A）；每城 2–5 個"]}
座標請依真實相對位置排列（北方在上）。只輸出 JSON。"""

OFFICER_PROMPT = """請只輸出一份 JSON 陣列（不要 markdown 圍欄、不要解說），列出{scope}，共約 {n} 位（含該陣營主要謀士、文官、水軍與名將；不要重複）。
每個元素欄位：
{{"id": "小寫拼音蛇形且全域唯一，如 zhou_yu", "name": "繁體中文名", "courtesy": "字（不確定寫 null）", "faction_path": ["依時間順序的所屬勢力，如 [\\"袁紹\\", \\"曹操\\"]"], "tags": ["猛將"|"統帥"|"謀士"|"政務"|"水軍"|"騎兵"|"外交"|"醫匠" 等，1–3 個], "home_city": "籍貫或主要活動城，須取自下列 id 之一：{cities}", "birth": 年份整數或 null, "death": 年份整數或 null, "summary": "一句話定位（≤30字，只寫廣為人知、無爭議的事實，不確定就寫較保守的說法）", "stats_estimate": {{"leadership": 0-100, "war": 0-100, "intellect": 0-100, "politics": 0-100}}}}
能力值是你依光榮《三國志》系列一般印象的估計，不確定就保守取中間值。只輸出 JSON。"""

BATCHES = [
    ("wei", "曹魏陣營（含早期曹操麾下與後期魏國）的武將與謀臣", 55),
    ("shu", "蜀漢陣營（含劉備早期勢力、荊州與益州班底）的武將與謀臣", 45),
    ("wu", "孫吳陣營（含孫堅、孫策、孫權時期）的武將與謀臣", 45),
    ("others", "群雄與其他勢力（董卓、呂布、袁紹、袁術、劉表、劉璋、公孫瓚、馬騰、張魯、孫策以外的江東與荊益豪傑等）的武將與謀臣", 50),
]


def ask(prompt: str, name: str) -> str:
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    pf = OUT / "raw" / f"{name}.prompt.md"; pf.write_text(prompt, encoding="utf-8")
    res = subprocess.run(["node", COMPANION, "ask", "--prompt-file", str(pf)], capture_output=True, text=True, timeout=900)
    (OUT / "raw" / f"{name}.out.txt").write_text(res.stdout, encoding="utf-8")
    return res.stdout


def parse_json(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON array in output")
    return json.loads(m.group())


def build_cities():
    cities = parse_json(ask(CITY_PROMPT, "cities"))
    for c in cities:
        c["verification"] = "unverified"
    (OUT / "cities.json").write_text(json.dumps(cities, ensure_ascii=False, indent=1), encoding="utf-8")
    print("cities", len(cities))


def build_officers():
    cities = json.loads((OUT / "cities.json").read_text(encoding="utf-8"))
    ids = ",".join(c["id"] for c in cities)
    for key, scope, n in BATCHES:
        try:
            data = parse_json(ask(OFFICER_PROMPT.format(scope=scope, n=n, cities=ids), f"officers_{key}"))
        except Exception as e:  # keep going; the validator and raw/ show what failed
            print("FAILED", key, e); continue
        for o in data:
            o["verification"] = "unverified"
        (OUT / f"officers_{key}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print("officers", key, len(data))

def postprocess():
    """Merge cross-batch duplicates, align ids with the in-game roster, and repair unknown home cities."""
    sys.path.insert(0, str(ROOT / "src"))
    from slg.engine.initial_state import build_initial_state
    game = {o.name: oid for oid, o in build_initial_state().officers.items()}
    cities = {c["id"] for c in json.loads((OUT / "cities.json").read_text(encoding="utf-8"))}
    files = sorted(OUT.glob("officers_*.json"))
    seen = {}
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        keep = []
        for o in data:
            if o["name"] in game:
                o["id"], o["in_game"] = game[o["name"]], True
            else:
                o["in_game"] = False
            if o["home_city"] not in cities:
                o["home_city_note"] = f"original value {o['home_city']!r} not in cities.json"
                o["home_city"] = "luoyang"
            if o["id"] in seen:
                first = seen[o["id"]]
                first["faction_path"] = list(dict.fromkeys(first.get("faction_path", []) + o.get("faction_path", [])))
                continue
            seen[o["id"]] = o
            keep.append(o)
        f.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("officers after merge:", len(seen))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what == "postprocess":
        postprocess(); sys.exit(0)
    if what in ("cities", "all"):
        build_cities()
    if what in ("officers", "all"):
        build_officers()
        postprocess()
