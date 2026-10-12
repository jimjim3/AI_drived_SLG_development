#!/usr/bin/env python3
"""Assemble the textbook PDF (and a single Markdown file) for one language.

  python3 build_book.py zh-TW out.pdf
  python3 build_book.py en out.pdf
Chapters are read from docs/textbook/<lang>/chNN_<slug>.md; [[FIG:id]] becomes the figure plus a numbered caption.
"""
import re
import sys
from pathlib import Path

import fitz
import markdown

sys.path.insert(0, str(Path(__file__).parent))
from book import BOOK, TITLE_EN, TITLE_ZH
from chapters import CHAPTERS, FIG_EN

FONT_DIR = Path.home() / ".fonts"
CH = sorted(CHAPTERS, key=lambda c: c["n"])
EXTRA = {"zh-TW": [("A", "appendix_a", "附錄"), ], "en": [("A", "appendix_a", "Appendices")]}


def css():
    f = FONT_DIR.as_posix()
    return f"""
@font-face {{ font-family: Body; src: url({f}/NotoSerifTC-Regular.ttf); font-weight: 400; }}
@font-face {{ font-family: Body; src: url({f}/NotoSerifTC-Bold.ttf); font-weight: 700; }}
@font-face {{ font-family: Head; src: url({f}/NotoSansTC-Bold.ttf); font-weight: 700; }}
* {{ font-family: Body; }}
body {{ font-size: 11.2px; line-height: 1.68; color: #1a1a1a; }}
h1, h2, h3, h4 {{ font-family: Head; font-weight: 700; color: #0d2b4e; page-break-after: avoid; }}
h1 {{ font-size: 22px; margin-top: 26px; border-bottom: 2px solid #0d2b4e; padding-bottom: 6px; }}
h2 {{ font-size: 15.5px; margin-top: 20px; }}
h3 {{ font-size: 13px; margin-top: 14px; }}
p {{ margin: 6px 0; text-align: left; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 8.5px; table-layout: fixed; }}
th, td {{ border: 1px solid #999; padding: 2px 3px; text-align: left; vertical-align: top; word-break: break-all; overflow-wrap: anywhere; }}
th {{ background: #dde6ef; font-family: Head; }}
code {{ font-family: monospace; background: #f0f0f0; padding: 1px 3px; font-size: 9.5px; }}
td code, th code {{ font-size: 7.8px; word-break: break-all; overflow-wrap: anywhere; white-space: normal; }}
pre {{ background: #f0f0f0; padding: 8px; font-size: 9px; overflow-wrap: break-word; white-space: pre-wrap; }}
blockquote {{ margin: 8px 0 8px 10px; padding-left: 8px; border-left: 3px solid #c9d2dc; color: #333; }}
div.fig {{ margin: 12px 0 14px 0; text-align: center; page-break-inside: avoid; }}
div.fig img {{ width: 100%; }}
div.cap {{ font-size: 9.6px; color: #333; margin-top: 3px; text-align: center; }}
.part {{ font-family: Head; font-size: 12px; color: #6b7280; letter-spacing: 1px; margin-top: 0; }}
.cover {{ text-align: center; margin-top: 150px; }}
.cover .t {{ font-family: Head; font-size: 28px; color: #0d2b4e; line-height: 1.4; }}
.cover .s {{ font-size: 14px; color: #444; margin-top: 18px; }}
.cover .d {{ font-size: 11px; color: #666; margin-top: 60px; }}
strong {{ font-weight: 700; }}
"""


def expand(md, lang, spec):
    figs = {f: (i + 1, cap) for i, (f, cap, _) in enumerate(spec["figures"])}

    def rep(m):
        fid = m.group(1)
        k, cap_zh = figs[fid]
        if lang == "zh-TW":
            label, cap = f"圖 {spec['n']}-{k}", cap_zh
        else:
            label, cap = f"Figure {spec['n']}-{k}", FIG_EN[fid]
        return f'\n<div class="fig"><img src="figures/{lang}/{fid}.png"/><div class="cap"><b>{label}</b>　{cap}</div></div>\n'
    return re.sub(r"^\s*\[\[FIG:([A-Za-z0-9_]+)\]\]\s*$", rep, md, flags=re.M)


def front(lang):
    if lang == "zh-TW":
        t, sub = TITLE_ZH, "從基礎原理、研究動機、實驗與結論到下一步規劃"
        note = (BOOK / "front_zh-TW.md")
        date = "2026 年 10 月"
    else:
        t, sub = TITLE_EN, "From first principles and motivation to experiments, conclusions and the next steps"
        note = (BOOK / "front_en.md")
        date = "October 2026"
    cover = f'<div class="cover"><div class="t">{t}</div><div class="s">{sub}</div><div class="d">{date}</div></div>'
    return cover, (note.read_text(encoding="utf-8") if note.exists() else "")


_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def fix_lists(text):
    """Python-Markdown only starts a list after a blank line; Qwen often writes the first item right under a paragraph."""
    out, fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        if (not fence and _ITEM.match(line) and out and out[-1].strip()
                and not _ITEM.match(out[-1]) and not out[-1].lstrip().startswith(("|", "#", ">"))
                and not out[-1].startswith((" ", "\t"))):
            out.append("")
        out.append(line)
    return "\n".join(out)


def chapter_files(lang):
    out = []
    for c in CH:
        p = BOOK / lang / f"ch{c['n']:02d}_{c['slug']}.md"
        out.append((c, p))
    return out


def build(lang, out_pdf):
    _md = lambda: markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    class _C:
        def convert(self, t): return _md().convert(fix_lists(t))
    mdx = lambda: _C()
    cover, preface = front(lang)
    parts, toc, full_md = [], [], []
    parts.append(("cover", cover, None))
    if preface:
        parts.append((("front", None), mdx().convert(preface), None))
        full_md.append(preface)
    last_part = None
    for c, p in chapter_files(lang):
        if not p.exists():
            print("MISSING", p, file=sys.stderr); continue
        text = expand(p.read_text(encoding="utf-8"), lang, c)
        part_label = c["part"] if lang == "zh-TW" else PART_EN.get(c["part"], c["part"])
        html = mdx().convert(text)
        if part_label != last_part:
            html = f'<p class="part">{part_label}</p>' + html; last_part = part_label
        parts.append((("chapter", c["n"]), html, text))
        full_md.append(f"<!-- part: {part_label} -->\n\n" + text)
    for name in ("appendix",):
        ap = BOOK / lang / f"{name}.md"
        if ap.exists():
            t = ap.read_text(encoding="utf-8"); parts.append((("appendix", name), mdx().convert(t), t)); full_md.append(t)
    (BOOK / f"book_{lang}.md").write_text("\n\n---\n\n".join(full_md), encoding="utf-8")

    writer = fitz.DocumentWriter(str(out_pdf))
    media = fitz.paper_rect("a4")
    where = media + (46, 52, -46, -56)
    page = 0
    for kind, html, _ in parts:
        story = fitz.Story(html=f"<html><body>{html}</body></html>", user_css=css(), archive=fitz.Archive(str(BOOK)))
        start = page
        more = 1
        while more:
            dev = writer.begin_page(media)
            more, _ = story.place(where)
            story.draw(dev); writer.end_page(); page += 1
            if page > 900: raise RuntimeError("runaway pagination")
        if isinstance(kind, tuple) and kind[0] == "chapter":
            toc.append((1, kind[1], start + 1))
    writer.close()
    stamp(out_pdf, toc, lang)
    print(f"wrote {out_pdf} ({page} pages)")


PART_EN = {
    "第一部分　動機與基礎": "Part I: Motivation and Foundations",
    "第二部分　設計與實作": "Part II: Design and Implementation",
    "第三部分　實驗與結果": "Part III: Experiments and Results",
    "第四部分　方法論與展望": "Part IV: Methodology and Outlook",
    "第一篇　動機與基礎": "Part I: Motivation and Foundations",
    "第二篇　設計與實作": "Part II: Design and Implementation",
    "第三篇　實驗與結果": "Part III: Experiments and Results",
    "第四篇　方法論與展望": "Part IV: Methodology and Outlook",
}


def stamp(pdf, toc, lang):
    doc = fitz.open(str(pdf))
    titles = {c["n"]: (f"第 {c['n']} 章　{c['title']}" if lang == "zh-TW" else f"Chapter {c['n']}  {c['title_en']}") for c in CH}
    doc.set_toc([[lvl, titles[n], pg] for lvl, n, pg in toc])
    for i, pg in enumerate(doc):
        if i == 0:
            continue
        r = pg.rect
        pg.insert_text((r.width / 2 - 8, r.height - 30), str(i), fontsize=9, color=(0.4, 0.4, 0.4))
    doc.subset_fonts()
    tmp = Path(pdf).with_suffix(".tmp.pdf")
    doc.save(str(tmp), garbage=4, deflate=True, deflate_fonts=True, use_objstms=1)
    doc.close(); tmp.replace(pdf)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(1)
    build(sys.argv[1], Path(sys.argv[2]))
