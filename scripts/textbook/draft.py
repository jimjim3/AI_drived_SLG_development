#!/usr/bin/env python3
"""Draft chapters with the local Qwen server (docs 3.4 style: direct API, scripted acceptance, automatic retries).

  python3 draft.py zh --chapters 2 3        draft Traditional-Chinese chapters from specs + sources
  python3 draft.py en --chapters 2 3        translate accepted zh chapters (docs/textbook/zh-TW/) to English
Outputs go to docs/textbook/drafts/<lang>/chNN.md with a chNN.meta.json holding every attempt's checks.
"""
import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import http.client
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book import BOOK, OUTLINE_TABLE, SYSTEM_EN, SYSTEM_ZH
from chapters import CHAPTERS
from check import check_en, check_zh, delatex, numbers, to_traditional

URL = "http://127.0.0.1:8090/v1/chat/completions"
TOKEN = (Path.home() / ".local/state/local-llm/api-token").read_text().strip()
MAX_TRIES = 3
NO_AUDIT = False


class ServerDown(RuntimeError):
    """The local Qwen server is not reachable. Someone else may have shut it down on purpose (it is a shared GPU), so we
    do NOT restart it: the run pauses, everything finished so far is on disk, and re-running resumes from there."""


def call(system, user, max_tokens, temperature=0.6):
    try:
        return _call(system, user, max_tokens, temperature)
    except (urllib.error.URLError, ConnectionError, http.client.HTTPException) as e:
        raise ServerDown(repr(e)) from e


def _call(system, user, max_tokens, temperature):
    body = json.dumps({"model": "qwen3.8-27b", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "max_tokens": max_tokens, "temperature": temperature, "top_p": 0.95, "chat_template_kwargs": {"enable_thinking": False}}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        d = json.load(r)
    ch = d["choices"][0]
    return ch["message"]["content"], ch.get("finish_reason"), d.get("usage", {})


def load_source(item):
    """A source is a path, or (path, start_marker, end_marker): the lines from the first line containing start_marker up to
    (not including) the first later line containing end_marker (None = to the end)."""
    if isinstance(item, (str, Path)):
        return Path(item).read_text(encoding="utf-8"), Path(item).name
    path, start, end = item
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    i = next(k for k, ln in enumerate(lines) if start in ln)
    j = next((k for k in range(i + 1, len(lines)) if end and end in lines[k]), len(lines))
    return "\n".join(lines[i:j]), f"{Path(path).name}（{start.strip()} 起）"


def read_sources(spec):
    parts, nums = [], set()
    for item in spec["sources"]:
        t, name = load_source(item)
        parts.append(f"=== 素材檔：{name} ===\n{t}")
        nums |= numbers(t)
    return "\n\n".join(parts), nums


def zh_prompt(spec):
    src, nums = read_sources(spec)
    figs = "\n".join(f"- 圖 {spec['n']}-{i + 1}：佔位符 [[FIG:{f}]]；內容：{cap}；放在第 {sec} 節" for i, (f, cap, sec) in enumerate(spec["figures"]))
    spec_nums = numbers(json.dumps(spec, ensure_ascii=False, default=str))
    user = f"""請撰寫全書第 {spec['n']} 章（{spec['part']}）。

章標題：{spec['title']}
本章在全書的位置：{spec['position']}

寫作大綱（逐節要點；可以調整順序與細節，但要涵蓋所有要點；每節都要有實質內容，不要只列清單）：
{spec['outline']}

必須出現的事實或數字（逐字）：{ '、'.join(spec.get('facts', [])) or '（無）'}

本章的圖（只能用這些，各一次）：
{figs}

長度：約 {spec['length'][0]}–{spec['length'][1]} 個中文字。
特別注意：{spec.get('notes', '（無）')}

{OUTLINE_TABLE}
以下是素材。它們是你唯一可信的事實來源；素材中的數字請逐字引用。

{src}
"""
    return user, nums | spec_nums


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


AUDIT_SYSTEM = "你是嚴格的技術審稿人，只依據提供的素材判斷，不憑印象。輸出必須是合法 JSON。"


def audit_and_revise(spec, text, src, out, n):
    figs = "\n".join(f"- 圖 {spec['n']}-{i + 1}（{f}）：{cap}" for i, (f, cap, _) in enumerate(spec["figures"])) or "（無）"
    audit_user = f"""下面是一章教科書草稿，以及唯一可信的素材。請逐段檢查草稿，只列出下列三類問題：
(a) 含有素材與章節規格中找不到依據的數字、具體事實、機制細節、材料或結論的句子；
(b) 與素材矛盾的句子；
(c) 把一般知識當成本專案事實、或圖說與圖的實際內容不符的句子。
輸出一個 JSON 陣列，每個元素是 {{"quote": 草稿中的原句（逐字，不超過 80 字）, "problem": 問題說明, "fix": "刪除" 或具體改寫建議}}；沒有問題就輸出 []。只輸出 JSON，不要其他文字。

=== 圖的實際內容（圖說只能描述這些）===
{figs}

=== 章節規格中的大綱 ===
{spec['outline']}

=== 素材 ===
{src}

=== 草稿 ===
{text}
"""
    try:
        raw, fin, _ = call(AUDIT_SYSTEM, audit_user, max_tokens=7000, temperature=0.2)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        issues = json.loads(raw)
    except Exception as e:
        log(f"ch{n} audit failed: {e!r}"); return text, None
    (out / f"ch{n:02d}.audit.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
    log(f"ch{n} audit: {len(issues)} issue(s)")
    if not issues:
        return text, issues
    rev_user = f"""下面是章節草稿與審稿意見（JSON）。請輸出修訂後的完整章節：只修改被指出的句子（刪除無依據的內容、改成素材中的準確說法，或在句末加註（一般知識）），其餘內容、段落結構、標題、佔位符 [[FIG:…]]、表格與數字一律不動。素材供查證。第一個字元就是 #，不要任何前言。

=== 審稿意見 ===
{json.dumps(issues, ensure_ascii=False, indent=1)}

=== 素材 ===
{src}

=== 草稿 ===
{text}
"""
    try:
        new, fin, _ = call(SYSTEM_ZH, rev_user, max_tokens=16000, temperature=0.3)
    except Exception as e:
        log(f"ch{n} revise failed: {e!r}"); return text, issues
    new = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", new.strip())
    if fin == "length":
        return text, issues
    return new, issues


def audit_only(spec, text, src, out, n):
    figs = "\n".join(f"- 圖 {spec['n']}-{i + 1}（{f}）：{cap}" for i, (f, cap, _) in enumerate(spec["figures"])) or "（無）"
    user = f"""下面是一章教科書草稿與唯一可信的素材。請逐段檢查，只列出：(a) 素材與章節規格中找不到依據的數字、具體事實、機制細節、材料或結論；(b) 與素材矛盾的句子；(c) 把一般知識當成本專案事實，或圖說與圖的實際內容不符的句子。
注意：章節規格（大綱與注意事項）中給出的事實與數字也算有依據；本書的章號以「章節對照表」為準，素材中的章號是舊報告的編號。
輸出 JSON 陣列，每個元素 {{"quote": 草稿原句（逐字，≤80 字）, "problem": 問題, "fix": "刪除" 或改寫建議}}；沒有問題輸出 []。只輸出 JSON。

=== 圖的實際內容 ===
{figs}

=== 章節規格 ===
大綱：{spec['outline']}
注意事項：{spec.get('notes', '')}
必備事實：{'、'.join(spec.get('facts', []))}

{OUTLINE_TABLE}
=== 素材 ===
{src}

=== 草稿 ===
{text}
"""
    try:
        raw, fin, _ = call(AUDIT_SYSTEM, user, max_tokens=7000, temperature=0.2)
        issues = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()))
    except Exception as e:
        log(f"ch{n} audit failed: {e!r}"); return None
    (out / f"ch{n:02d}.audit.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1))
    log(f"ch{n} audit (advisory): {len(issues)} issue(s)")
    return issues


def finished(lang, n):
    d = BOOK / "drafts" / ("zh-TW" if lang == "zh" else "en")
    mp, tp = d / f"ch{n:02d}.meta.json", d / f"ch{n:02d}.md"
    if not (mp.exists() and tp.exists()):
        return False
    att = [a for a in json.loads(mp.read_text()) if a.get("try") != "revise"]
    return bool(att) and not att[-1].get("hard") and "error" not in att[-1] and not att[-1].get("paused")


def draft_zh(spec):
    n = spec["n"]
    out = BOOK / "drafts" / "zh-TW"; out.mkdir(parents=True, exist_ok=True)
    user, nums = zh_prompt(spec)
    attempts, best = [], None
    feedback = ""
    for k in range(1, MAX_TRIES + 1):
        t0 = time.time()
        try:
            text, fin, usage = call(SYSTEM_ZH, user + feedback, max_tokens=16000, temperature=0.6 if k == 1 else 0.5)
        except ServerDown as e:
            log(f"ch{n}: PAUSED, server unreachable ({e}); not restarting it"); return n, [{"try": k, "paused": True, "error": str(e)}]
        except Exception as e:
            log(f"ch{n} try {k}: API error {e!r}"); attempts.append({"try": k, "error": repr(e)}); continue
        text = to_traditional(delatex(re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())))
        hard, warn, info = check_zh(text, spec, nums)
        if fin == "length": hard.append("hit max_tokens (truncated)")
        att = {"try": k, "seconds": round(time.time() - t0), "finish": fin, "usage": usage, "hard": hard, "warn": warn, **info}
        attempts.append(att)
        log(f"ch{n} try {k}: {info['cjk_chars']} chars, {len(hard)} hard {hard[:3]}, unknown nums {len(info['unknown_numbers'])}, {att['seconds']}s")
        key = (len(hard), len(info["unknown_numbers"]))
        if best is None or key < best[0]:
            best = (key, text)
        (out / f"ch{n:02d}.try{k}.md").write_text(text, encoding="utf-8")
        if hard:
            feedback = "\n\n【上一版沒有通過自動檢查，請在這一版全部修正（不要提到這件事）】\n" + "\n".join(f"- {h}" for h in hard) + "\n- 每個 ## 小節請寫到至少 3 段；用語、數字與素材逐字一致；矩陣不要用 LaTeX。"
        if not hard:
            break
    if best:
        text = best[1]
        if best[0][0] == 0 and not NO_AUDIT:                                   # drafted cleanly: audit against the sources, then revise once
            src, _ = read_sources(spec)
            issues = audit_only(spec, text, src, out, n)                       # advisory only: its judgments were wrong too often to apply automatically
        (out / f"ch{n:02d}.md").write_text(text, encoding="utf-8")
    (out / f"ch{n:02d}.meta.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=1))
    return n, attempts


def draft_en(spec):
    n = spec["n"]
    zh_path = BOOK / "zh-TW" / f"ch{n:02d}_{spec['slug']}.md"
    zh = zh_path.read_text(encoding="utf-8")
    out = BOOK / "drafts" / "en"; out.mkdir(parents=True, exist_ok=True)
    glossary = (BOOK / "glossary_zh_en.md").read_text(encoding="utf-8") if (BOOK / "glossary_zh_en.md").exists() else ""
    user = (f"Translate this chapter into English.\n\nTerm glossary (use these renderings consistently):\n{glossary}\n\n=== CHAPTER (Traditional Chinese) ===\n{zh}\n")
    attempts, best = [], None
    for k in range(1, MAX_TRIES + 1):
        t0 = time.time()
        try:
            text, fin, usage = call(SYSTEM_EN, user, max_tokens=16000, temperature=0.3)
        except ServerDown as e:
            log(f"en ch{n}: PAUSED, server unreachable ({e}); not restarting it"); return n, [{"try": k, "paused": True, "error": str(e)}]
        except Exception as e:
            log(f"en ch{n} try {k}: API error {e!r}"); attempts.append({"try": k, "error": repr(e)}); continue
        text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())
        hard, warn, info = check_en(text, zh, spec)
        if fin == "length": hard.append("hit max_tokens (truncated)")
        attempts.append({"try": k, "seconds": round(time.time() - t0), "hard": hard, "warn": warn, **info})
        log(f"en ch{n} try {k}: {len(text.split())} words, {len(hard)} hard {hard[:3]}")
        key = len(hard)
        if best is None or key < best[0]:
            best = (key, text)
        if not hard:
            break
    if best:
        (out / f"ch{n:02d}.md").write_text(best[1], encoding="utf-8")
    (out / f"ch{n:02d}.meta.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=1))
    return n, attempts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("lang", choices=["zh", "en"])
    ap.add_argument("--chapters", type=int, nargs="*")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--no-audit", action="store_true")
    ap.add_argument("--force", action="store_true", help="redo chapters that already passed their checks")
    a = ap.parse_args()
    NO_AUDIT = a.no_audit
    specs = [c for c in CHAPTERS if not a.chapters or c["n"] in a.chapters]
    if not a.force:
        done = [c["n"] for c in specs if finished(a.lang, c["n"])]
        if done:
            log(f"skipping chapters already accepted: {done} (use --force to redo)")
        specs = [c for c in specs if c["n"] not in done]
    fn = draft_zh if a.lang == "zh" else draft_en
    with cf.ThreadPoolExecutor(max_workers=a.threads) as ex:
        for n, att in ex.map(fn, specs):
            ok = att and not att[-1].get("hard") and "error" not in att[-1]
            paused = att and att[-1].get("paused")
            log(f"== chapter {n}: {'PAUSED (server down; rerun to resume)' if paused else 'ACCEPTED' if ok else 'NEEDS REVIEW'} after {len(att)} attempt(s)")
