"""Ask an LLM (NIM) to classify the Koei-table expansion candidates (faction, career path, home city, birth/death).

Reads data/sanguo/candidates_officers.json (name, courtesy, bio, Koei games) and writes the answers back into the same
file as `faction` (wei|shu|wu|others), `faction_path`, `home_city` (id from cities.json or null), `birth`, `death`,
`classification` = "llm_unverified". Nothing here is verified against sources; the model is told to answer null when unsure.
Resumable: officers already classified are skipped.
"""
import json, os, sys, time, urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "data" / "sanguo"
URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = os.environ.get("NIM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
KEY = os.environ["NVIDIA_API_KEY"]
BATCH = 20


def ask(prompt):
    body = {"model": MODEL, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}, "max_tokens": 6000,
            "messages": [{"role": "system", "content": "/no_think"}, {"role": "user", "content": prompt}]}
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=180))["choices"][0]["message"]["content"]
        except Exception as e:
            print("retry", e, file=sys.stderr); time.sleep(5)
    return None


def main():
    path = D / "candidates_officers.json"
    cands = json.load(open(path))
    cities = {c["id"]: c["name"] for c in json.load(open(D / "cities.json"))}
    city_list = "、".join(f"{k}={v}" for k, v in cities.items())
    todo = [c for c in cands if "classification" not in c]
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        rows = [{"name": c["name"], "courtesy": c.get("courtesy"), "bio": c.get("bio")} for c in chunk]
        prompt = ("以下是三國時代人物(含少數可能是三國以外的人物)。請依你有把握的史實判斷每人:\n"
                  "- faction:曹魏/司馬晉系=wei,蜀漢=shu,孫吳=wu,其餘(群雄如袁紹、董卓、呂布、劉表,或不屬三國)=others;"
                  "取其在三國時代最主要的歸屬。\n"
                  "- faction_path:依序效力過的主君(中文陣列,例如[\"袁紹\",\"曹操\"]),不確定則 []。\n"
                  f"- home_city:籍貫或主要根據地最接近的城池 id,只能從這份清單選:{city_list};不確定或不在清單附近則 null。\n"
                  "- birth、death:西元年整數,不知道就 null。\n"
                  "沒把握的欄位一律給 null(或 []),不要編造。只輸出 JSON 陣列,與輸入同序,每項 "
                  "{\"name\":..,\"faction\":..,\"faction_path\":[..],\"home_city\":..,\"birth\":..,\"death\":..}。\n"
                  + json.dumps(rows, ensure_ascii=False))
        out = ask(prompt)
        print(i, "->", (out or "FAIL")[:60].replace("\n", " "), file=sys.stderr, flush=True)
        if out is None:
            continue
        s, e = out.find("["), out.rfind("]")
        try:
            ans = {a["name"]: a for a in json.loads(out[s:e + 1])}
        except Exception:
            print("parse failure in batch", i, file=sys.stderr)
            continue
        for c in chunk:
            a = ans.get(c["name"])
            if not a:
                continue
            c["faction"] = a.get("faction") if a.get("faction") in ("wei", "shu", "wu", "others") else None
            c["faction_path"] = a.get("faction_path") or []
            c["home_city"] = a.get("home_city") if a.get("home_city") in cities else None
            c["birth"], c["death"] = a.get("birth"), a.get("death")
            c["classification"] = "llm_unverified"
        json.dump(cands, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)  # save after every batch
    done = sum(1 for c in cands if "classification" in c)
    print(f"{done}/{len(cands)} classified")


main()
