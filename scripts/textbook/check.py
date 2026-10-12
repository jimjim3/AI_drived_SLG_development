"""Automatic acceptance checks for drafted and translated chapters (no GPU needed)."""
import re
import sys
import unicodedata

CJK = re.compile(r"[㐀-鿿]")
NUM = re.compile(r"(?<![A-Za-z_\d.])\d[\d,]*(?:\.\d+)?")
FIG = re.compile(r"\[\[FIG:([A-Za-z0-9_]+)\]\]")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿]")


def _plain(m):
    """Convert one LaTeX math fragment to readable plain text."""
    t = m
    t = re.sub(r"\\begin\{[bp]?matrix\}(.*?)\\end\{[bp]?matrix\}", lambda x: "[" + "; ".join(" ".join(c.strip() for c in r.split("&")) for r in x.group(1).split("\\\\") if r.strip()) + "]", t, flags=re.S)
    t = re.sub(r"\\text(?:bf|rm|it)?\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\math(?:rm|bf|it)\{([^{}]*)\}", r"\1", t)
    for _ in range(3):
        t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1) / (\2)", t)
    for k, v in {"\\times": "×", "\\approx": "≈", "\\cdot": "·", "\\leq": "≤", "\\le": "≤", "\\geq": "≥", "\\ge": "≥", "\\neq": "≠", "\\sum": "Σ",
                 "\\quad": " ", "\\qquad": "  ", "\\,": " ", "\\;": " ", "\\!": "", "\\%": "%", "\\_": "_", "\\left": "", "\\right": "", "\\lceil": "⌈", "\\rceil": "⌉",
                 "\\lfloor": "⌊", "\\rfloor": "⌋", "\\log": "log", "\\mu": "µ", "\\to": "→", "\\rightarrow": "→", "\\land": "AND", "\\wedge": "AND", "\\oplus": "XOR", "\\ldots": "…", "\\dots": "…"}.items():
        t = t.replace(k.replace("\\\\", "\\"), v)
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)
    t = re.sub(r"\\([&#])", r"\1", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def delatex(text):
    """Display math ($$…$$) becomes an indented plain-text line; inline $…$ becomes plain text."""
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: "\n\n    " + _plain(m.group(1)).replace("\n", " ") + "\n\n", text, flags=re.S)
    text = re.sub(r"\$([^$\n]+)\$", lambda m: _plain(m.group(1)), text)
    return text


def to_traditional(text):
    """Character-level simplified -> traditional conversion (leaves traditional text unchanged)."""
    try:
        import opencc
    except ImportError:
        return text
    return opencc.OpenCC("s2t").convert(text)


def norm_num(s):
    return s.replace(",", "").rstrip(".")


def numbers(text):
    return {norm_num(m) for m in NUM.findall(text)}


def simplified_fraction(text):
    try:
        import opencc
    except ImportError:
        return 0.0
    cv = opencc.OpenCC("s2t")
    chars = [c for c in text if CJK.match(c)]
    if not chars:
        return 0.0
    changed = sum(1 for c in chars if cv.convert(c) != c)
    return changed / len(chars)


def repeated_substring(text, n=24, limit=3):
    seen = {}
    t = re.sub(r"\s+", "", text)
    for i in range(0, max(0, len(t) - n), 4):
        s = t[i:i + n]
        seen[s] = seen.get(s, 0) + 1
    worst = max(seen.values()) if seen else 0
    return worst > limit, worst


def section_items(text, heading):
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    if not m:
        return None
    return [ln for ln in m.group(1).splitlines() if re.match(r"\s*(?:\d+[\.\)、]|[-*•])\s*\S", ln)]


def check_zh(text, spec, source_numbers):
    """Returns (hard_failures, warnings, info). Hard failures cause a retry."""
    hard, warn, info = [], [], {}
    body = text.strip()
    cj = len(CJK.findall(body)); info["cjk_chars"] = cj
    lo, hi = 2800, int(spec["length"][1] * 1.3)
    if cj < lo: hard.append(f"too short: {cj} < {lo}")
    if cj > hi: hard.append(f"too long: {cj} > {hi}")
    if not body.startswith("# "): hard.append("does not start with '# '")
    elif not re.match(rf"# 第\s*{spec['n']}\s*章", body): hard.append("title line is not '# 第 N 章：…'")
    if re.match(r"\s*(好的|以下是|當然|沒問題|我將|我會|這是)", body): hard.append("preamble")
    for h in ("本章學習目標", "本章重點", "習題"):
        if not re.search(rf"^##\s+{h}\s*$", body, re.M): hard.append(f"missing section '## {h}'")
    secs = re.findall(rf"^##\s+{spec['n']}\.\d+\s", body, re.M)
    if len(secs) < 5: hard.append(f"only {len(secs)} numbered sections")
    ex = section_items(body, "習題")
    if ex is not None and not (4 <= len(ex) <= 8): hard.append(f"{len(ex)} exercises (want 5-6)")
    summary = section_items(body, "本章重點")
    if summary is not None and not (4 <= len(summary) <= 10): warn.append(f"{len(summary)} summary points")
    want = [f[0] for f in spec["figures"]]
    got = FIG.findall(body)
    if sorted(got) != sorted(want): hard.append(f"figure placeholders {got} != {want}")
    for f in want:
        if f"圖 {spec['n']}-" not in body: hard.append("no 'Figure N-k' reference in prose"); break
    sf = simplified_fraction(body); info["simplified_fraction"] = round(sf, 4)
    if sf > 0.004: hard.append(f"simplified characters {sf:.2%}")
    rep, worst = repeated_substring(body)
    if rep: hard.append(f"repeated text ({worst}x a 24-char run)")
    if re.search(r"\\[A-Za-z]+|\$", body): hard.append("LaTeX math")
    if EMOJI.search(body): hard.append("emoji")
    tail = body.splitlines()[-1].strip() if body else ""
    if ex is not None and ex and not re.search(r"[。？！）)\.\?」”a-zA-Z0-9]$", tail): hard.append(f"looks truncated: ...{tail[-30:]}")
    for fact in spec.get("facts", []):
        if fact not in body: hard.append(f"missing required fact: {fact}")
    unknown = []
    prose = re.sub(r"^#.*$", "", body, flags=re.M)                       # headings
    prose = re.sub(r"^\s*(?:\d+[\.\)、])\s+", "", prose, flags=re.M)         # list markers
    prose = re.sub(r"圖\s*\d+-\d+|第\s*\d+\s*章|\b\d+\.\d+\s*節|§\s*\d+(?:\.\d+)*|\b\d+\.\d+\s*(?=[節、，,（(])", " ", prose)
    UNIT = r"(?:V|pJ|nJ|ns|µs|us|ms|fF|pF|KB|MB|GB|B|F²|%|×|週期|位元|bit|bits|cycles|MHz|GHz|nm|µW|µA|pA|mm²|µm|倍)"
    for m in re.finditer(rf"(\d[\d,]*(?:\.\d+)?)\s*[-–~～至到]\s*(\d[\d,]*(?:\.\d+)?)\s*{UNIT}|(\d[\d,]*(?:\.\d+)?)\s*{UNIT}", prose):
        for g in m.groups():
            if g and norm_num(g) not in source_numbers:
                unknown.append(norm_num(g))
    for m in NUM.finditer(prose):
        v = norm_num(m.group(0))
        if v in source_numbers: continue
        try:
            x = float(v)
        except ValueError:
            continue
        if x == int(x) and x <= 12: continue
        unknown.append(v)
    info["unknown_numbers"] = sorted(set(unknown), key=lambda s: float(s))
    unnumbered = [h for h in re.findall(r"^##\s+(.+)$", body, re.M) if not re.match(rf"({spec['n']}\.\d+\s|本章學習目標|本章重點|習題)", h)]
    if unnumbered: hard.append(f"unnumbered ## sections: {unnumbered[:3]}")
    if len(set(unknown)) > 6: hard.append(f"{len(set(unknown))} numbers not in sources/spec: {info['unknown_numbers'][:10]}")
    return hard, warn, info


def check_en(en, zh, spec):
    hard, warn, info = [], [], {}
    body = en.strip()
    if not body.startswith("# "): hard.append("does not start with '# '")
    if re.match(r"\s*(Sure|Here is|Here's|Certainly|Below is)", body): hard.append("preamble")
    h2z, h2e = len(re.findall(r"^##\s", zh, re.M)), len(re.findall(r"^##\s", body, re.M))
    if h2z != h2e: hard.append(f"## heading count {h2e} != {h2z}")
    h3z, h3e = len(re.findall(r"^###\s", zh, re.M)), len(re.findall(r"^###\s", body, re.M))
    if h3z != h3e: hard.append(f"### heading count {h3e} != {h3z}")
    if sorted(FIG.findall(zh)) != sorted(FIG.findall(body)): hard.append("figure placeholders differ")
    leftover = CJK.findall(re.sub(r"`[^`]*`", "", body))
    if leftover: hard.append(f"{len(leftover)} CJK characters left: {''.join(leftover[:12])}")
    nz, ne = numbers(zh), numbers(body)
    missing = sorted(n for n in nz - ne if not (float(n) == int(float(n)) and float(n) < 20))
    extra = sorted(n for n in ne - nz if not (float(n) == int(float(n)) and float(n) < 20))
    info["numbers_missing_in_en"], info["numbers_extra_in_en"] = missing, extra
    if len(missing) > 3: hard.append(f"numbers dropped in translation: {missing[:10]}")
    if len(extra) > 6: warn.append(f"numbers added in translation: {extra[:10]}")
    zt = len(re.findall(r"^\|", zh, re.M)); et = len(re.findall(r"^\|", body, re.M))
    if zt != et: hard.append(f"table rows {et} != {zt}")
    ratio = len(body.split()) / max(1, len(CJK.findall(zh))); info["words_per_cjk_char"] = round(ratio, 3)
    if not (0.35 <= ratio <= 0.95): hard.append(f"length ratio {ratio:.2f} out of range")
    rep, worst = repeated_substring(body.lower(), n=40)
    if rep: hard.append(f"repeated text ({worst}x)")
    if EMOJI.search(body): hard.append("emoji")
    return hard, warn, info
