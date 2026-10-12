#!/usr/bin/env python3
"""Where is the textbook? Per chapter: zh draft state, English draft state, editorial state. Run any time; needs no GPU."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book import BOOK
from chapters import CHAPTERS


def draft_state(lang, n):
    d = BOOK / "drafts" / ("zh-TW" if lang == "zh" else "en")
    mp = d / f"ch{n:02d}.meta.json"
    if not mp.exists():
        return "-"
    att = [a for a in json.loads(mp.read_text()) if a.get("try") != "revise"]
    if not att:
        return "-"
    last = att[-1]
    if last.get("paused"): return "PAUSED"
    if last.get("hard") or "error" in last: return "FAIL"
    return f"ok({last.get('cjk_chars', '')})" if lang == "zh" else "ok"


print(f"{'ch':>3} {'slug':<22} {'zh draft':<10} {'zh final':<9} {'en draft':<9} {'en final':<9} {'audit':<6}")
for c in sorted(CHAPTERS, key=lambda c: c["n"]):
    n, slug = c["n"], c["slug"]
    zf = (BOOK / "zh-TW" / f"ch{n:02d}_{slug}.md").exists()
    ef = (BOOK / "en" / f"ch{n:02d}_{slug}.md").exists()
    ap = BOOK / "drafts" / "zh-TW" / f"ch{n:02d}.audit.json"
    au = len(json.loads(ap.read_text())) if ap.exists() else "-"
    print(f"{n:>3} {slug:<22} {draft_state('zh', n):<10} {'EDITED' if zf else '-':<9} {draft_state('en', n):<9} {'EDITED' if ef else '-':<9} {au!s:<6}")
