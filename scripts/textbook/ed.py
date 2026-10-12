"""Editorial pass helper: apply (old, new) replacements to a Qwen draft and write the edited chapter.
Every replacement must match exactly once (or `count` times); a missing anchor is an error, never silently skipped."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from book import BOOK
from chapters import CHAPTERS


def apply(n, reps, tail=None):
    spec = next(c for c in CHAPTERS if c["n"] == n)
    text = (BOOK / "drafts" / "zh-TW" / f"ch{n:02d}.md").read_text(encoding="utf-8")
    text = re.sub(r"^# 第\s*\d+\s*章[：:]?\s*.*$", f"# 第 {n} 章　{spec['title']}", text, count=1, flags=re.M)
    for r in reps:
        old, new = r[0], r[1]
        cnt = r[2] if len(r) > 2 else 1
        if hasattr(old, "subn"):                                  # compiled regex
            text, found = old.subn(new, text)
        else:
            found = text.count(old)
            text = text.replace(old, new)
        if found != cnt:
            raise SystemExit(f"ch{n}: anchor found {found}x (expected {cnt}): {str(old)[:70]!r}")
    if tail:
        text = text.rstrip() + "\n" + tail
    out = BOOK / "zh-TW" / f"ch{n:02d}_{spec['slug']}.md"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out.name}: {len(text)} chars")
