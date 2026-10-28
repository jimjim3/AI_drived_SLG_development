"""Draw theatre maps from real lon/lat (data/sanguo/maps/geo_agy.json, agy-reported, unverified)."""
import json, math
from pathlib import Path
M = Path(__file__).resolve().parent.parent / "data" / "sanguo" / "maps"
G = json.load(open(M / "geo_agy.json"))
W, H = 1100, 850
GOLD, TXT, RIVER = "#fbbf24", "#e8d9b0", "#2f6fa3"

THEATRES = {
    "chibi": dict(title="赤壁之戰", sub="公元208年 · 依真實經緯度繪製", box=(111.2, 115.6, 29.0, 31.4),
        pts=["襄陽", "長坂", "江陵", "夏口", "樊口", "烏林", "赤壁", "柴桑"],
        side={"烏林": "N", "夏口": "N", "襄陽": "N", "長坂": "N", "江陵": "S", "樊口": "S", "赤壁": "S", "柴桑": "S"},
        arrow=("烏林", "赤壁")),
    "guandu": dict(title="官渡之戰", sub="公元200年 · 依真實經緯度繪製", box=(112.2, 116.4, 33.6, 36.6),
        pts=["鄴", "黎陽", "白馬", "延津", "官渡", "烏巢", "陳留", "許昌", "倉亭"],
        side={"鄴": "N", "黎陽": "N", "倉亭": "N", "白馬": "N", "延津": "N", "烏巢": "N", "官渡": "S", "陳留": "S", "許昌": "S"},
        arrow=("官渡", "烏巢")),
}


def build(name, t):
    x0, x1, y0, y1 = t["box"]
    kx = W / (x1 - x0)
    ky = kx * math.cos(math.radians((y0 + y1) / 2))  # px per degree of latitude (equirectangular, local)
    ky = min(ky * 1.0, H / (y1 - y0))
    ox = (W - kx * (x1 - x0)) / 2
    oy = (H - ky * (y1 - y0)) / 2
    P = lambda lo, la: (ox + (lo - x0) * kx, oy + (y1 - la) * ky)
    line = lambda pts, col, w, extra="": ("<polyline fill='none' stroke='%s' stroke-width='%s' stroke-linecap='round' stroke-linejoin='round' %s points='%s'/>"
        % (col, w, extra, " ".join("%.0f,%.0f" % P(*p) for p in pts)))
    o = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}'>",
         "<rect width='1100' height='850' fill='#0b1220'/>",
         f"<clipPath id='c'><rect width='{W}' height='{H}'/></clipPath><g clip-path='url(#c)'>"]
    # sea: polygon east of coast
    coast = G["coast"] + [[130, G["coast"][-1][1]], [130, G["coast"][0][1]]]
    o.append("<polygon fill='#0e2a44' points='%s'/>" % " ".join("%.0f,%.0f" % P(*p) for p in coast))
    for k, c, w in (("yangtze", RIVER, 9), ("yellow_river", "#b8863b", 8), ("han_river", RIVER, 5)):
        o.append(line(G[k], c, w))
    names = t["pts"]
    for n in names:
        px, py = P(*G["places"][n])
        dy = -16 if t["side"].get(n) == "N" else 28
        o.append(f"<circle cx='{px:.0f}' cy='{py:.0f}' r='7' fill='{GOLD}' stroke='#0b1220' stroke-width='2'/>")
        o.append(f"<text x='{px:.0f}' y='{py + dy:.0f}' fill='{TXT}' font-size='20' text-anchor='middle' font-family='serif' paint-order='stroke' stroke='#0b1220' stroke-width='4'>{n}</text>")
    a, b = (P(*G["places"][n]) for n in t["arrow"])
    o.append(f"<line x1='{a[0]:.0f}' y1='{a[1]:.0f}' x2='{b[0]:.0f}' y2='{b[1]:.0f}' stroke='#f97316' stroke-width='3' stroke-dasharray='8 6'/>")
    o.append("</g>")
    o.append(f"<text x='40' y='70' fill='{TXT}' font-size='44' font-family='serif'>{t['title']}</text>")
    o.append(f"<text x='42' y='100' fill='#94a3b8' font-size='18'>{t['sub']}(河道為 agy 回報之概略位置,未經核對;黃=黃河、藍=長江/漢水)</text>")
    o.append("<text x='1040' y='60' fill='#94a3b8' font-size='18' text-anchor='middle'>北 ↑</text></svg>")
    (M / f"{name}.svg").write_text("\n".join(o), encoding="utf-8")


for k, v in THEATRES.items():
    build(k, v)
print("ok")
