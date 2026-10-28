"""Ask an LLM (NIM) to fact-check data/sanguo officers; writes flags only, never edits the dataset."""
import json, os, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "sanguo"
URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = os.environ.get("NIM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
KEY = os.environ["NVIDIA_API_KEY"]
BATCH = 12


def ask(prompt):
    body = {"model": MODEL, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}, "max_tokens": 3000,
            "messages": [{"role": "system", "content": "/no_think"},
                         {"role": "user", "content": prompt}]}
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    for i in range(3):
        try:
            return json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
        except Exception as e:
            print("retry", e, file=sys.stderr); time.sleep(5)
    return None


def main():
    officers = []
    for f in ("wei", "shu", "wu", "others"):
        officers += json.load(open(ROOT / f"officers_{f}.json"))
    cities = {c["id"]: c["name"] for c in json.load(open(ROOT / "cities.json"))}
    flags = []
    for i in range(0, len(officers), BATCH):
        rows = [{"id": o["id"], "name": o["name"], "courtesy": o.get("courtesy"), "birth": o.get("birth"),
                 "death": o.get("death"), "home_city": cities.get(o.get("home_city"), o.get("home_city")),
                 "faction_path": o.get("faction_path")} for o in officers[i:i + BATCH]]
        p = ("以下是三國武將資料。請只依你有把握的史實,找出『明顯錯誤』的欄位(生卒年差>2年、字錯、籍貫城池明顯不符、陣營歸屬錯)。"
             "沒把握就不要標。只輸出 JSON 陣列,每項 {\"id\":..,\"field\":..,\"problem\":..,\"suggest\":..};無錯則輸出 []。\n"
             + json.dumps(rows, ensure_ascii=False))
        out = ask(p)
        print(i, "->", (out or "FAIL")[:80].replace("\n", " "), file=sys.stderr)
        if out is None:
            continue
        s, e = out.find("["), out.rfind("]")
        try:
            flags += json.loads(out[s:e + 1])
        except Exception:
            flags.append({"id": f"batch{i}", "field": "parse", "problem": out[:300]})
    json.dump({"model": MODEL, "verification": "llm_flagged_unconfirmed", "flags": flags},
              open(ROOT / "crosscheck_nim.json", "w"), ensure_ascii=False, indent=1)
    print(len(officers), "officers,", len(flags), "flags")


main()
