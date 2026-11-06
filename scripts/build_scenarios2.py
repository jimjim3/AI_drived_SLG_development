#!/usr/bin/env python3
"""Second pass over the agy-built scenarios (data only, nothing here is read by the engine; everything unverified).

  patch   — the 4 eras whose full rewrite came back empty are fixed by asking agy for a short *patch* instead
  officers— give records to the officer names that appear in scenarios but not in the database (agy; may answer "no such person")
  nimcheck— an independent review of every scenario by NVIDIA Nemotron (a different model family than the agy author/reviewer)
  summary — compare the two reviews per era

Resumable. Usage: python3 scripts/build_scenarios2.py [patch|officers|nimcheck|summary|all]   (nimcheck needs NVIDIA_API_KEY)
"""
import importlib.util
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bs", ROOT / "scripts" / "build_scenarios.py")
bs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bs)
D, X = bs.D, bs.X
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = os.environ.get("NIM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")


def known_names():
    names = set()
    for f in ("officers_wei", "officers_shu", "officers_wu", "officers_others", "candidates_officers"):
        names |= {o["name"] for o in json.load(open(D / f"{f}.json"))}
    return names


def best_scenario(eid):
    p = X / "scenarios_fixed" / f"{eid}.json"
    return json.load(open(p if p.exists() else X / "scenarios" / f"{eid}.json"))


# --- patch ---------------------------------------------------------------------------------------------------------
def apply_patch(sc, patch):
    facs = {f["id"]: f for f in sc["factions"]}
    for op in patch.get("set_city_owner", []):
        city, to = op.get("city"), op.get("to")
        for f in sc["factions"]:
            if city in f["cities"]:
                f["cities"].remove(city)
        if city in sc.get("neutral_cities", []):
            sc["neutral_cities"].remove(city)
        if to in facs:
            facs[to]["cities"].append(city)
        else:
            sc.setdefault("neutral_cities", []).append(city)
    for op in patch.get("remove_officer", []):
        for f in sc["factions"]:
            f["officers"] = [o for o in f["officers"] if o.get("name") != op.get("name")]
    for op in patch.get("move_officer", []):
        for f in sc["factions"]:
            for o in f["officers"]:
                if o.get("name") == op.get("name"):
                    o["city"] = op.get("city", o["city"])
    for op in patch.get("add_officer", []):
        f = facs.get(op.get("faction"))
        if f is not None and not any(o.get("name") == op.get("name") for o in f["officers"]):
            f["officers"].append({"name": op["name"], "city": op.get("city", f["capital"]), "role": op.get("role", "武將")})
    return sc


def stage_patch():
    cities = bs.city_brief()
    brief = json.dumps(cities, ensure_ascii=False)
    check = bs.check_scenario(cities)
    todo = [e for e in bs.ERAS if (X / "reviews" / f"{e[0]}.json").exists() and not (X / "scenarios_fixed" / f"{e[0]}.json").exists()
            and (X / "scenarios" / f"{e[0]}.json").exists()]

    def one(era):
        eid, year, name = era
        sc = json.load(open(X / "scenarios" / f"{eid}.json"))
        issues = json.load(open(X / "reviews" / f"{eid}.json")).get("issues", [])
        prompt = (
            f"以下是策略遊戲「{year} 年・{name}」劇本草稿與審稿意見。不要重寫整個劇本;只輸出「修補指令」JSON,只含你認同的修正:\n"
            '{"set_city_owner":[{"city":"城id","to":"勢力id 或 neutral"}],"remove_officer":[{"name":"武將名"}],'
            '"move_officer":[{"name":"武將名","city":"城id"}],"add_officer":[{"faction":"勢力id","name":"武將名","city":"城id","role":"武將"}]}\n'
            "沒有要改的鍵就給空陣列。城 id 必須在城池清單內,勢力 id 必須是草稿中存在的勢力。只輸出 JSON。\n\n"
            f"城池清單:\n{brief}\n\n草稿:\n{json.dumps(sc, ensure_ascii=False)}\n\n審稿意見:\n{json.dumps(issues, ensure_ascii=False)}")
        patch = bs.run_json(prompt, f"patch_{eid}", lambda d: [] if isinstance(d, dict) else ["需為 JSON 物件"])
        if not isinstance(patch, dict):
            return
        fixed = apply_patch(sc, patch)
        fixed["repaired"], fixed["repair_method"] = True, "patch"
        problems = check(fixed)
        bs.log(f"patch_{eid}", f"{sum(len(v) for v in patch.values())} ops, {len(problems)} problems")
        if not problems:
            bs.save(X / "scenarios_fixed" / f"{eid}.json", fixed)

    bs.pmap(one, todo)


# --- officers ------------------------------------------------------------------------------------------------------
def stage_officers():
    known = known_names()
    koei = {o["name"]: o for o in json.load(open(D / "koei_stats.json"))["officers"]}
    seen = {}
    for p in sorted((X / "scenarios").glob("*.json")) + sorted((X / "scenarios_fixed").glob("*.json")):
        sc = json.load(open(p))
        for f in sc["factions"]:
            for o in f["officers"]:
                n = o.get("name")
                if n and n not in known and n != "候選" and len(n) <= 4:
                    seen.setdefault(n, set()).add(f"{sc['year']}:{f['lord']}")
    names = sorted(seen)
    city_ids = [{"id": c["id"], "name": c["name"]} for c in json.load(open(X / "cities_ext.json"))]
    out_path = X / "officers_ext.json"
    done = json.load(open(out_path)) if out_path.exists() else {}
    todo = [n for n in names if n not in done]
    batches = [todo[i:i + 12] for i in range(0, len(todo), 12)]

    def one(args):
        i, batch = args
        rows = [{"name": n, "seen_in": sorted(seen[n])[:4]} for n in batch]
        prompt = (
            "以下是三國時代劇本中出現的人名,附出現的年份與所屬君主。請為每人建立遊戲武將資料。"
            "若你不認得、或認為這不是歷史上的三國人物,就回 {\"name\":..,\"exists\":false},不要編造。\n"
            "存在者格式:{\"name\",\"exists\":true,\"courtesy\":\"字或null\",\"birth\":年或null,\"death\":年或null,"
            "\"faction_path\":[\"曆任勢力\"],\"home_city\":\"城id或null\",\"tags\":[\"猛將|智將|統帥|內政|...\"],"
            "\"bio\":\"一句話\",\"stats_estimate\":{\"war\":0-100,\"leadership\":0-100,\"intelligence\":0-100,\"politics\":0-100,\"charm\":0-100}}\n"
            "stats 請以光榮《三國志》的相對強弱為準(名將 85+,一般將領 55–75,小人物 30–55)。home_city 只能用下列城 id。"
            "輸出與輸入同序的 JSON 陣列,只輸出 JSON。\n\n人名:\n" + json.dumps(rows, ensure_ascii=False)
            + "\n\n城池 id:\n" + json.dumps(city_ids, ensure_ascii=False))
        data = bs.run_json(prompt, f"officers_{i}", lambda d: [] if isinstance(d, list) else ["需為 JSON 陣列"])
        for r in data or []:
            if isinstance(r, dict) and r.get("name") in batch:
                r["seen_in"] = sorted(seen[r["name"]])
                r["verification"] = "unverified"
                if r["name"] in koei:
                    r["koei_mean"] = koei[r["name"]].get("mean")
                done[r["name"]] = r
        bs.save(out_path, done)
        bs.log(f"officers_{i}", f"{len(done)}/{len(names)}")

    bs.pmap(one, list(enumerate(batches)))
    bs.save(out_path, done)
    ex = [r for r in done.values() if r.get("exists") is not False]
    bs.log("officers", f"{len(done)} answered, {len(ex)} exist, {len(done) - len(ex)} marked as not real")


# --- nimcheck ------------------------------------------------------------------------------------------------------
def ask_nim(prompt):
    body = {"model": NIM_MODEL, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}, "max_tokens": 6000,
            "messages": [{"role": "system", "content": "/no_think"}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request(NIM_URL, json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]
        except Exception as e:
            bs.log("nim", f"retry {e}")
            time.sleep(5)


def stage_nimcheck():
    brief = json.dumps(bs.city_brief(), ensure_ascii=False)

    def one(era):
        eid, year, name = era
        out_path = X / "reviews_nim" / f"{eid}.json"
        if out_path.exists() or not (X / "scenarios" / f"{eid}.json").exists():
            return
        sc = best_scenario(eid)
        prompt = (
            f"你是嚴格的三國史審稿人。以下是策略遊戲「{year} 年・{name}」劇本的開局設定(另一個模型寫的草稿)。請找出史實錯誤:"
            "武將在該年尚未出生/已死亡/尚未出仕、武將放在錯誤勢力或城池、城池歸屬與實況不符、漏掉重要勢力、strength 排序不合理。\n"
            '輸出 JSON 物件:{"verdict":"ok|minor|major","issues":[{"severity":"high|medium|low","type":"officer|city|faction|other",'
            '"detail":"問題(點名武將或城)","fix":"建議改法"}]}。沒把握的不要列。只輸出 JSON。\n\n'
            f"城池清單:\n{brief}\n\n劇本:\n{json.dumps(sc, ensure_ascii=False)}")
        out = ask_nim(prompt)
        if not out:
            return
        try:
            s, e = out.find("{"), out.rfind("}")
            data = json.loads(out[s:e + 1])
        except Exception as ex:
            bs.log(f"nim_{eid}", f"parse failure {ex}")
            return
        bs.save(out_path, data)
        bs.log(f"nim_{eid}", f"{data.get('verdict')} {len(data.get('issues', []))} issues")

    bs.pmap(one, bs.ERAS)


def stage_summary():
    rows = []
    for eid, year, name in bs.ERAS:
        a, n = X / "reviews" / f"{eid}.json", X / "reviews_nim" / f"{eid}.json"
        if not (a.exists() and n.exists()):
            continue
        ra, rn = json.load(open(a)), json.load(open(n))
        names = set(re.findall(r"[一-鿿]{2,4}", " ".join(i.get("detail", "") for i in rn.get("issues", []))))
        both = sorted({w for i in ra.get("issues", []) for w in re.findall(r"[一-鿿]{2,4}", i.get("detail", ""))} & names)
        rows.append({"era": eid, "year": year, "name": name,
                     "agy": {"verdict": ra.get("verdict"), "issues": len(ra.get("issues", []))},
                     "nim": {"verdict": rn.get("verdict"), "issues": len(rn.get("issues", []))},
                     "high_nim": [i for i in rn.get("issues", []) if i.get("severity") == "high"],
                     "shared_terms": both[:20]})
    bs.save(X / "crosscheck_summary.json", rows)
    bs.log("summary", f"{len(rows)} eras; nim verdicts " + str({v: sum(1 for r in rows if r['nim']['verdict'] == v) for v in ('ok', 'minor', 'major')}))


STAGES = {"patch": stage_patch, "officers": stage_officers, "nimcheck": stage_nimcheck, "summary": stage_summary}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name in (STAGES if which == "all" else [which]):
        bs.log("stage", name)
        STAGES[name]()
