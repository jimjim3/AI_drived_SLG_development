"""Cut a 3x3 portrait sheet with magenta (#FF00FF) gutters into per-officer PNGs.
Usage: python3 scripts/cut_sheet.py sheet.png id1,id2,...,id9 outdir [size=256]"""
import sys, pathlib
import numpy as np
from PIL import Image

sheet, ids, out = sys.argv[1], sys.argv[2].split(","), pathlib.Path(sys.argv[3])
size = int(sys.argv[4]) if len(sys.argv) > 4 else 256
assert len(ids) == 9, "need 9 ids"
im = Image.open(sheet).convert("RGB"); a = np.asarray(im).astype(int)
m = (abs(a[:, :, 0] - 255) < 60) & (a[:, :, 1] < 80) & (abs(a[:, :, 2] - 255) < 60)

def spans(v, n=3, th=0.6):
    g = []; s = None
    for i, x in enumerate(v):
        if x > th and s is None: s = i
        if x <= th and s is not None: g.append((s, i)); s = None
    if s is not None: g.append((s, len(v)))
    cells = [(g[i][1], g[i + 1][0]) for i in range(len(g) - 1)]
    if len(cells) != n: raise SystemExit(f"expected {n} cells, found {len(cells)} (gutters {g})")
    return cells

cs, rs = spans(m.mean(0)), spans(m.mean(1)); out.mkdir(parents=True, exist_ok=True); k = 0
for (y0, y1) in rs:
    for (x0, x1) in cs:
        c = im.crop((x0 + 2, y0 + 2, x1 - 2, y1 - 2)); s = min(c.size); c = c.crop((0, 0, s, s)).resize((size, size), Image.LANCZOS)
        c.save(out / f"{ids[k]}.png", optimize=True); k += 1
print("wrote", k, "portraits to", out)
