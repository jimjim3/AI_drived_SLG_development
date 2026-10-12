"""Shared style for the textbook figures. LANG is 'zh-TW' or 'en'; every label goes through T(zh, en)."""
import os
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONT_VF = pathlib.Path.home() / ".fonts" / "NotoSansTC-VF.ttf"
if FONT_VF.exists():
    fe_normal = fm.FontEntry(fname=str(FONT_VF), name="NotoSansTC-VF", weight="normal")
    fe_bold = fm.FontEntry(fname=str(FONT_VF), name="NotoSansTC-VF", weight="bold")
    fm.fontManager.ttflist.insert(0, fe_bold)
    fm.fontManager.ttflist.insert(0, fe_normal)
    font_family = "NotoSansTC-VF"
else:
    font_family = "sans-serif"

plt.rcParams.update({
    "font.family": font_family, "axes.unicode_minus": False, "figure.dpi": 100, "savefig.dpi": 170,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 11,
    "axes.labelsize": 10, "legend.fontsize": 8.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
})
LANG = os.environ.get("TEXTBOOK_LANG", "zh-TW")
OUT = ROOT / "docs" / "textbook" / "figures" / LANG
OUT.mkdir(parents=True, exist_ok=True)

NAVY, ORANGE, GREEN, RED, GREY, LIGHT, PURPLE = "#0d2b4e", "#d9822b", "#2f7d5b", "#b8342f", "#6b7280", "#e8eef5", "#6d4aa5"
CYCLE = [NAVY, ORANGE, GREEN, RED, PURPLE, GREY]


def T(zh, en):
    return zh if LANG == "zh-TW" else en


def save(fig, name):
    target = OUT / f"{name}.png"
    fig.savefig(target, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", target)
    if LANG == "zh-TW":
        en_out = ROOT / "docs" / "textbook" / "figures" / "en"
        en_out.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(target, en_out / f"{name}.png")


def box(ax, x, y, w, h, text, fc=LIGHT, ec=NAVY, fs=9, bold=False, tc="black", lw=1.2, r=0.02):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.005,rounding_size={r}", fc=fc, ec=ec, lw=lw))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc,
            fontweight="bold" if bold else "normal", linespacing=1.25)


def arrow(ax, x0, y0, x1, y1, color=NAVY, lw=1.4, style="-|>", ms=11, ls="-"):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=ms, color=color, lw=lw, linestyle=ls))
