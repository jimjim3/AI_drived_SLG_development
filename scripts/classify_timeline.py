"""Time-aware allegiance for the expansion candidates, answered independently by two models (NIM Nemotron Ultra and agy Gemini)
and cross-checked. Allegiance changes over time, so each officer gets a list of affiliations
  {"from": year|null, "to": year|null, "lord": str, "relation": "subordinate" | "nominal_ally" | "independent"}
and a faction at reference years (190, 200, 208, 220): wei | shu | wu | others | none (not yet active / already dead).
`nominal_ally` = a titular alliance or joint-leader relation without direct rule (e.g. Yuan Shao as head of the anti-Dong coalition).

Writes into data/sanguo/candidates_officers.json: `timeline_nim`, `timeline_agy` (each {affiliations, at}), `faction_at` (years on which the
two models agree), `needs_review` (years on which they disagree). Resumable per model. Nothing is verified against sources.
"""
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data" / "sanguo"
YEARS = ("190", "200", "208", "220")
URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = os.environ.get("NIM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
AGY = sorted(Path.home().glob(".claude/plugins/cache/agy-staff/agy/*/companion/agy-companion.mjs"))[-1]


def prompt_for(rows):
    return ("以下是三國時代人物(含少數可能不屬三國)。歸屬會隨時間變化,請依你有把握的史實,為每人給出:\n"
            "- affiliations:依時間排序的歸屬段落,每段 {\"from\":起始年或null,\"to\":結束年或null,\"lord\":主君/勢力(中文),"
            "\"relation\":\"subordinate\"(直屬部下)|\"nominal_ally\"(名義上的同盟或共主,無直接統治,例如反董卓聯軍盟主袁紹)|\"independent\"(自立或割據)}。\n"
            "- at:四個年份各自所屬陣營:\"190\",\"200\",\"208\",\"220\"。值為 wei(曹操/曹魏/司馬氏)|shu(劉備/蜀漢)|wu(孫策孫權/孫吳)|"
            "others(其他群雄、割據者或不屬三國)|none(尚未出仕、年幼或已死亡)。\n"
            "沒把握就給 \"others\" 或 null,不要編造。只輸出 JSON 陣列,與輸入同序,每項 {\"name\":..,\"affiliations\":[..],\"at\":{..}}。\n"
            + json.dumps(rows, ensure_ascii=False))


def parse(out, names):
    s, e = out.find("["), out.rfind("]")
    ans = json.loads(out[s:e + 1])
    return {a["name"]: {"affiliations": a.get("affiliations") or [], "at": {y: (a.get("at") or {}).get(y) for y in YEARS}}
            for a in ans if a.get("name") in names}


def ask_nim(prompt):
    body = {"model": NIM_MODEL, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}, "max_tokens": 8000,
            "messages": [{"role": "system", "content": "/no_think"}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=240))["choices"][0]["message"]["content"]
        except Exception as e:
            print("nim retry", e, file=sys.stderr); time.sleep(5)


def ask_agy(prompt):
    f = D / "raw" / "_timeline_prompt.txt"
    f.write_text(prompt, encoding="utf-8")
    for _ in range(2):
        r = subprocess.run(["node", str(AGY), "ask", "--prompt-file", str(f)], capture_output=True, text=True, timeout=600)
        if r.stdout.strip():
            return r.stdout
        print("agy empty output, retry", file=sys.stderr)


def run_model(label, key, asker, batch, cands):
    todo = [c for c in cands if key not in c]
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        rows = [{"name": c["name"], "courtesy": c.get("courtesy"), "bio": c.get("bio")} for c in chunk]
        out = asker(prompt_for(rows))
        print(label, i, "->", (out or "FAIL")[:50].replace("\n", " "), file=sys.stderr, flush=True)
        if not out:
            continue
        try:
            ans = parse(out, {c["name"] for c in chunk})
        except Exception as e:
            print(label, "parse failure", i, e, file=sys.stderr)
            continue
        for c in chunk:
            if c["name"] in ans:
                c[key] = ans[c["name"]]
        json.dump(cands, open(D / "candidates_officers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    cands = json.load(open(D / "candidates_officers.json"))
    which = sys.argv[1:] or ["nim", "agy"]
    if "nim" in which:
        run_model("nim", "timeline_nim", ask_nim, 15, cands)
    if "agy" in which:
        run_model("agy", "timeline_agy", ask_agy, 30, cands)
    both = 0
    for c in cands:
        a, b = c.get("timeline_nim"), c.get("timeline_agy")
        if not (a and b):
            continue
        both += 1
        c["faction_at"] = {y: a["at"][y] for y in YEARS if a["at"][y] == b["at"][y] and a["at"][y]}
        c["needs_review"] = [y for y in YEARS if a["at"][y] != b["at"][y]]
    json.dump(cands, open(D / "candidates_officers.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_dis = sum(1 for c in cands if c.get("needs_review"))
    print(f"both models answered for {both}/{len(cands)}; officers with at least one disagreeing year: {n_dis}")


main()
