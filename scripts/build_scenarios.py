#!/usr/bin/env python3
"""Expand the Three Kingdoms database with agy (Gemini): a ~110-city map and ~29 era scenarios.

Data only: nothing here is read by the game engine. Everything is model memory, unverified.
Outputs go to data/sanguo/ext/:
  cities_ext.json          master city list (existing 40 ids kept unchanged, new ones added), with a Koei-style size tier
  adjacency_ext.json       symmetric neighbour lists over the master list
  scenarios/<era id>.json  one scenario per era (who owns which city, key officers, opening text, events)
  reviews/<era id>.json    an independent agy review of each scenario (anachronisms, ownership errors)
  scenarios_fixed/<era>.json  scenario after applying the review's issues

Stages (each resumable; re-running skips finished outputs):  cities | adjacency | eras | review | repair | validate | all
"""
import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "sanguo"
X = D / "ext"
AGY = sorted(Path.home().glob(".claude/plugins/cache/agy-staff/agy/*/companion/agy-companion.mjs"))[-1]
MODEL = "gemini-3.8-flash-medium"
WORKERS = 8
_lock = threading.Lock()

GROUPS = {
    "north": ["冀州", "幽州", "并州", "青州"],
    "central": ["司隸", "兗州", "豫州", "徐州"],
    "south": ["荊州", "揚州", "交州"],
    "west": ["涼州", "益州"],
}

ERAS = [
    ("e184", 184, "黃巾之亂"), ("e189", 189, "董卓入京"), ("e190", 190, "反董卓聯軍"),
    ("e192", 192, "王允誅董卓、李傕郭汜亂長安"), ("e194", 194, "曹操征徐州、呂布奪兗州"),
    ("e196", 196, "曹操迎獻帝遷許"), ("e197", 197, "袁術稱帝"), ("e198", 198, "下邳之戰、呂布敗亡"),
    ("e199", 199, "孫策據江東、官渡前夜"), ("e200", 200, "官渡之戰"), ("e202", 202, "袁紹病逝、袁氏兄弟內鬥"),
    ("e205", 205, "曹操平定河北"), ("e207", 207, "三顧茅廬、北征烏桓"), ("e208", 208, "赤壁之戰前夜"),
    ("e211", 211, "潼關之戰、劉備入蜀"), ("e214", 214, "劉備取益州"), ("e215", 215, "合肥之戰、張魯降曹"),
    ("e217", 217, "濡須口、漢中之戰前夜"), ("e219", 219, "劉備稱漢中王、關羽水淹七軍"), ("e220", 220, "曹丕篡漢"),
    ("e222", 222, "夷陵之戰"), ("e225", 225, "諸葛亮南征"), ("e228", 228, "諸葛亮北伐"), ("e234", 234, "五丈原"),
    ("e249", 249, "高平陵之變"), ("e255", 255, "毌丘儉之亂、姜維北伐"), ("e263", 263, "魏滅蜀"),
    ("e265", 265, "晉代魏"), ("e280", 280, "晉滅吳、天下一統"),
]


def ask(prompt, tag):
    f = X / "_prompts" / f"{tag}.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(prompt, encoding="utf-8")
    for attempt in range(3):
        try:
            r = subprocess.run(["node", str(AGY), "ask", "--model", MODEL, "--prompt-file", str(f)],
                               capture_output=True, text=True, timeout=900)
        except subprocess.TimeoutExpired:
            r = None
        if r and r.stdout.strip():
            return r.stdout
        log(tag, f"empty output (attempt {attempt + 1})")
    return None


def log(tag, msg):
    with _lock:
        print(f"[{tag}] {msg}", file=sys.stderr, flush=True)


def parse_json(out):
    out = re.sub(r"```(?:json)?", "", out)
    starts = [i for i in (out.find("{"), out.find("[")) if i >= 0]
    s = min(starts)
    e = max(out.rfind("}"), out.rfind("]"))
    return json.loads(out[s:e + 1])


def run_json(prompt, tag, check):
    """Ask, parse, validate with check(data)->list of problems; on problems retry once with them quoted."""
    note = ""
    for _ in range(3):
        out = ask(prompt + note, tag)
        if not out:
            return None
        try:
            data = parse_json(out)
        except Exception as e:
            note = f"\n\n上次輸出無法解析為 JSON({e});請只輸出合法 JSON。"
            log(tag, f"parse failure: {e}")
            continue
        problems = check(data)
        if not problems:
            return data
        log(tag, f"{len(problems)} problems: {problems[:3]}")
        note = "\n\n上次輸出有以下問題,請修正後重新輸出完整 JSON:\n- " + "\n- ".join(problems[:15])
    return data  # best effort; validate stage will report what remains


def pmap(fn, items):
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(fn, items))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# --- stage: cities -------------------------------------------------------------------------------------------------
def stage_cities():
    base = json.load(open(D / "cities.json"))
    anchors = [{"id": c["id"], "name": c["name"], "region": c["region"], "x": c["x"], "y": c["y"]} for c in base]

    def one(item):
        gname, regions = item
        out_path = X / "_cities" / f"{gname}.json"
        if out_path.exists():
            return json.load(open(out_path))
        mine = [c for c in base if c["region"] in regions]
        prompt = (
            "你是三國史地專家。我正在為策略遊戲建立東漢末到三國時代的城池地圖。\n"
            f"請列出屬於以下各州的主要城池/郡治/重要關隘與港口,目標 {len(regions) * 7} 到 {len(regions) * 9} 座:{'、'.join(regions)}。\n"
            "規則:\n"
            "1. 下列「既有城池」必須原樣保留(id、name、region、x、y、terrain、role 都不改),並且仍要出現在輸出中。\n"
            "2. 新增城池的 id 用小寫漢語拼音(無聲調、無空格),不得與既有 id(含其他州)重複;name 用繁體中文。\n"
            "3. x、y 用與下列「全圖座標參考」相同的概略座標系(x 向東增加,y 向南增加),新城的相對位置要合理,不要與既有城重疊(至少相距 0.15)。\n"
            "4. size 依光榮《三國志》規模分級:xl(特大,僅洛陽/長安/成都/建業等少數)、l(大)、m(中)、s(小)。\n"
            "5. 只收錄 184–280 年間確實存在的重要地點;不確定就不要列。\n"
            "輸出一個 JSON 陣列,每項:{\"id\",\"name\",\"region\",\"x\",\"y\",\"terrain\":[...],\"role\":\"一句話\",\"size\":\"xl|l|m|s\"}。只輸出 JSON。\n\n"
            "既有城池(必須保留):\n" + json.dumps(mine, ensure_ascii=False) +
            "\n\n全圖座標參考(所有既有城):\n" + json.dumps(anchors, ensure_ascii=False))
        keep = {c["id"] for c in mine}

        def check(data):
            if not isinstance(data, list):
                return ["輸出必須是 JSON 陣列"]
            ids = [c.get("id") for c in data]
            p = [f"缺少既有城 {i}" for i in sorted(keep - set(ids))]
            p += [f"id 重複 {i}" for i in set(ids) if ids.count(i) > 1]
            p += [f"{c.get('id')} 的 size 不合法" for c in data if c.get("size") not in ("xl", "l", "m", "s")]
            return p

        data = run_json(prompt, f"cities_{gname}", check)
        if data:
            save(out_path, data)
        return data

    res = pmap(one, list(GROUPS.items()))
    merged, seen = [], set()
    by_id = {c["id"]: c for c in base}
    for grp in res:
        for c in grp or []:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            old = by_id.get(c["id"])
            merged.append({**c, **{k: old[k] for k in ("name", "region", "x", "y", "terrain", "role") if old and k in old}})
    for c in base:  # any existing city the model dropped
        if c["id"] not in seen:
            merged.append({**c, "size": c.get("size") or "m"})
    for c in merged:
        c["verification"] = "unverified"
        c["existing"] = c["id"] in by_id
    save(X / "cities_ext.json", merged)
    log("cities", f"{len(merged)} cities ({len(base)} existing)")


# --- stage: adjacency ----------------------------------------------------------------------------------------------
def stage_adjacency():
    cities = json.load(open(X / "cities_ext.json"))
    ids = {c["id"] for c in cities}
    base = {c["id"]: c["neighbors"] for c in json.load(open(D / "cities.json"))}
    compact = [{"id": c["id"], "name": c["name"], "region": c["region"], "x": c["x"], "y": c["y"]} for c in cities]

    def one(item):
        gname, regions = item
        out_path = X / "_adj" / f"{gname}.json"
        if out_path.exists():
            return json.load(open(out_path))
        mine = [c["id"] for c in cities if c["region"] in regions]
        prompt = (
            "以下是東漢末三國時代的城池清單(id、名稱、州、概略座標)。請為我指定的城池給出「陸路或水路可直接行軍抵達的相鄰城池」,"
            "每城 2 到 5 個,只能使用清單中的 id,必須包含跨州的合理連接(關隘、渡口、河道),不要連接遙遠而無直接道路的城。\n"
            f"需要回答的城池 id:{json.dumps(mine)}\n"
            "輸出 JSON 物件:{城池id:[相鄰id,...]}。只輸出 JSON。\n\n城池清單:\n" + json.dumps(compact, ensure_ascii=False))

        def check(data):
            if not isinstance(data, dict):
                return ["輸出必須是 JSON 物件"]
            p = [f"缺少 {i}" for i in mine if i not in data]
            p += [f"{k} 的相鄰 {v} 不在清單中" for k, vs in data.items() for v in vs if v not in ids]
            return p

        data = run_json(prompt, f"adj_{gname}", check)
        if data:
            save(out_path, data)
        return data

    res = pmap(one, list(GROUPS.items()))
    adj = {i: set() for i in ids}
    for i, ns in base.items():
        adj[i].update(n for n in ns if n in ids)
    for grp in res:
        for k, vs in (grp or {}).items():
            if k in adj:
                adj[k].update(v for v in vs if v in ids and v != k)
    for k, vs in list(adj.items()):  # symmetrise
        for v in vs:
            adj[v].add(k)
    save(X / "adjacency_ext.json", {k: sorted(v) for k, v in sorted(adj.items())})
    log("adjacency", f"{sum(len(v) for v in adj.values()) // 2} edges")


# --- stage: eras ---------------------------------------------------------------------------------------------------
def city_brief():
    return [{"id": c["id"], "name": c["name"], "region": c["region"], "size": c["size"]}
            for c in json.load(open(X / "cities_ext.json"))]


def check_scenario(cities):
    ids = {c["id"] for c in cities}

    def check(data):
        if not isinstance(data, dict) or "factions" not in data:
            return ["輸出必須是含 factions 的 JSON 物件"]
        owned = {}
        p = []
        for f in data["factions"]:
            for c in f.get("cities", []):
                if c not in ids:
                    p.append(f"{f.get('id')} 擁有的 {c} 不在城池清單")
                elif c in owned:
                    p.append(f"{c} 同時屬於 {owned[c]} 與 {f.get('id')}")
                owned[c] = f.get("id")
            if f.get("capital") not in ids:
                p.append(f"{f.get('id')} 的 capital {f.get('capital')} 不在清單")
        neutral = set(data.get("neutral_cities", []))
        p += [f"neutral 的 {c} 不在清單" for c in neutral if c not in ids]
        p += [f"{c} 同時是中立與 {owned[c]} 的城" for c in neutral & set(owned)]
        missing = sorted(ids - set(owned) - neutral)
        if missing:
            p.append(f"這些城既不屬任何勢力也不在 neutral_cities:{missing}")
        return p

    return check


SCHEMA = (
    '{"id":"e200","year":200,"name":"官渡之戰","summary_zh":"≤120字背景",'
    '"factions":[{"id":"f_caocao","lord":"曹操","side":"wei|shu|wu|jin|others","capital":"城id","playable":true,'
    '"strength":"S|A|B|C|D","cities":["城id",...],"officers":[{"name":"武將名","city":"所在城id","role":"君主|謀士|武將|..."}]}],'
    '"neutral_cities":["城id",...],"opening_zh":"≤150字開場白,以史官口吻","goal_zh":"一句話勝利目標",'
    '"events":[{"turn":回合數(從1起),"text_zh":"史實事件"}],"difficulty":1到5}'
)


def stage_eras():
    cities = city_brief()
    brief = json.dumps(cities, ensure_ascii=False)

    def one(era):
        eid, year, name = era
        out_path = X / "scenarios" / f"{eid}.json"
        if out_path.exists():
            return
        prompt = (
            f"你是三國史專家。請為策略遊戲設計「{year} 年・{name}」這個劇本的開局態勢(以該年年初為準)。\n"
            "要求:\n"
            "1. 逐城指定歸屬:下列清單的每一座城都必須恰好出現一次,在某勢力的 cities 或 neutral_cities(空城/無主/小勢力散落者)之中。\n"
            "2. 勢力 3 到 12 個,涵蓋當時真正有實力的君主;每個勢力 officers 列 8 到 20 位當時確實在其麾下、"
            "且已出仕的重要武將(用通行繁體中文名),city 指其所在城;不確定就不要列,不要編造,不要放尚未出生或已死亡的人。\n"
            "3. side 為 wei(曹魏系)/shu(蜀漢系)/wu(孫吳系)/jin(晉)/others(其他群雄或朝廷)。\n"
            "4. strength 依該勢力在當時的實力相對排序:S 最強,D 最弱。playable 表示適合讓玩家扮演。\n"
            "5. events 列 3 到 6 個之後數年內可能觸發的史實事件,turn 用回合數(1 回合約一季,四回合一年)。\n"
            "6. 只依你有把握的史實;沒有把握的歸屬用 neutral_cities。\n"
            f"輸出單一 JSON 物件,格式範例(示意用,內容請換成本劇本):{SCHEMA}\n只輸出 JSON。\n\n城池清單:\n{brief}")
        data = run_json(prompt, f"era_{eid}", check_scenario(cities))
        if data:
            data.setdefault("id", eid)
            data["year"], data["verification"] = year, "unverified"
            save(out_path, data)
            log(f"era_{eid}", f"{len(data.get('factions', []))} factions")

    pmap(one, ERAS)


# --- stage: review + repair ----------------------------------------------------------------------------------------
def stage_review():
    brief = json.dumps(city_brief(), ensure_ascii=False)

    def one(era):
        eid, year, name = era
        src, out_path = X / "scenarios" / f"{eid}.json", X / "reviews" / f"{eid}.json"
        if out_path.exists() or not src.exists():
            return
        sc = json.load(open(src))
        prompt = (
            f"你是嚴格的三國史審稿人。以下是策略遊戲「{year} 年・{name}」劇本的開局設定(模型草稿)。請找出史實錯誤,"
            "例如:武將在該年尚未出生/已死亡/尚未出仕、武將放在錯誤勢力或錯誤城池、城池歸屬與當時實況不符、"
            "漏掉當時重要勢力、勢力 strength 排序不合理。\n"
            "輸出 JSON 物件:{\"verdict\":\"ok|minor|major\",\"issues\":[{\"severity\":\"high|medium|low\",\"type\":\"officer|city|faction|other\","
            "\"detail\":\"問題\",\"fix\":\"建議改法(具體到武將名、城id、勢力id)\"}]}。沒把握的不要列。只輸出 JSON。\n\n"
            f"城池清單:\n{brief}\n\n劇本:\n{json.dumps(sc, ensure_ascii=False)}")
        data = run_json(prompt, f"review_{eid}", lambda d: [] if isinstance(d, dict) and "issues" in d else ["需含 issues"])
        if data:
            save(out_path, data)
            log(f"review_{eid}", f"{data.get('verdict')} {len(data.get('issues', []))} issues")

    pmap(one, ERAS)


def stage_repair():
    cities = city_brief()
    brief = json.dumps(cities, ensure_ascii=False)

    def one(era):
        eid, year, name = era
        src, rev, out_path = X / "scenarios" / f"{eid}.json", X / "reviews" / f"{eid}.json", X / "scenarios_fixed" / f"{eid}.json"
        if out_path.exists() or not (src.exists() and rev.exists()):
            return
        sc, issues = json.load(open(src)), json.load(open(rev)).get("issues", [])
        if not [i for i in issues if i.get("severity") in ("high", "medium")]:
            save(out_path, sc)
            return
        prompt = (
            f"以下是策略遊戲「{year} 年・{name}」劇本草稿與審稿意見。請依意見修正(只修有把握的;審稿意見若自己有誤就不採納),"
            "輸出修正後的完整劇本 JSON,格式與草稿完全相同,城池清單中每座城仍須恰好出現一次。只輸出 JSON。\n\n"
            f"城池清單:\n{brief}\n\n草稿:\n{json.dumps(sc, ensure_ascii=False)}\n\n審稿意見:\n{json.dumps(issues, ensure_ascii=False)}")
        data = run_json(prompt, f"repair_{eid}", check_scenario(cities))
        if data:
            data.setdefault("id", eid)
            data["year"], data["verification"] = year, "unverified"
            data["repaired"] = True
            save(out_path, data)

    pmap(one, ERAS)


# --- stage: validate -----------------------------------------------------------------------------------------------
def stage_validate():
    cities = json.load(open(X / "cities_ext.json"))
    ids = {c["id"] for c in cities}
    adj = json.load(open(X / "adjacency_ext.json"))
    problems = []
    for k, vs in adj.items():
        problems += [f"adjacency asymmetric {k}-{v}" for v in vs if k not in adj.get(v, [])]
    seen, stack = set(), [next(iter(ids))]
    while stack:
        c = stack.pop()
        if c not in seen:
            seen.add(c)
            stack += adj.get(c, [])
    problems += [f"disconnected city {c}" for c in sorted(ids - seen)]
    problems += [f"{c['id']}: bad size" for c in cities if c.get("size") not in ("xl", "l", "m", "s")]
    check = check_scenario(cities)
    names = set()
    for f in ("officers_wei", "officers_shu", "officers_wu", "officers_others", "candidates_officers"):
        names |= {o["name"] for o in json.load(open(D / f"{f}.json"))}
    n_sc, unresolved = 0, {}
    for sub in ("scenarios", "scenarios_fixed"):
        for p in sorted((X / sub).glob("*.json")):
            sc = json.load(open(p))
            n_sc += 1
            problems += [f"{sub}/{p.stem}: {x}" for x in check(sc)]
            for f in sc.get("factions", []):
                for o in f.get("officers", []):
                    if o.get("name") not in names:
                        unresolved.setdefault(o.get("name"), set()).add(p.stem)
    print(f"{len(cities)} cities, {sum(len(v) for v in adj.values()) // 2} edges, {n_sc} scenario files checked")
    print(f"{len(problems)} structural problems"); [print(" ", x) for x in problems[:40]]
    print(f"{len(unresolved)} officer names not in the database/candidates (first 40):", sorted(unresolved)[:40])


STAGES = {"cities": stage_cities, "adjacency": stage_adjacency, "eras": stage_eras, "review": stage_review,
          "repair": stage_repair, "validate": stage_validate}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name in (STAGES if which == "all" else [which]):
        log("stage", name)
        STAGES[name]()
