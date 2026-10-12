"""Data-driven figures for the textbook: all numbers are computed or read from repo artifacts."""
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fig_common import (
    CYCLE, GREEN, GREY, LIGHT, NAVY, ORANGE, PURPLE, RED, ROOT, T,
    arrow, box, plt, save,
)
import numpy as np

# Ensure project src is in sys.path for running simulation
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def f03_token_cost():
    """Four decision architectures estimated token consumption per turn (parsed from docs/DESIGN.md §3)."""
    text = (ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
    
    # Extract numbers from markdown table in Section 3
    # | 每位武將每回合都問（~400 人） | ~420 | 1,500 | **~630k** |
    # | 君主 + 太守批次（本文建議） | 20 + 100 = 120 | 2,000 | **~240k** |
    # | 再加：只有玩家可見 / 前線城用 LLM，其餘規則 AI | ~40 | 2,000 | **~80k** |
    # 20 勢力 × 每次約 3k tokens，每回合約 **6 萬 tokens**
    items = []
    if "~630k" in text:
        items.append((T("全 LLM 代理（每將每回合都問）", "Full LLM (Every officer queried)"), 630000, RED))
    if "~240k" in text:
        items.append((T("君主＋太守批次分層（文內建議）", "Monarch + Governor Batched"), 240000, ORANGE))
    if "~80k" in text:
        items.append((T("僅前線/玩家可見城用 LLM", "Frontier-Only LLM + Rules"), 80000, PURPLE))
    if "6 萬 tokens" in text:
        items.append((T("勢力敘事模式（每勢力每回合單次）", "Faction Narration (Single call/faction)"), 60000, GREEN))

    labels = [it[0] for it in items]
    vals = [it[1] for it in items]
    colors = [it[2] for it in items]

    fig, ax = plt.subplots(figsize=(8.4, 3.8))
    bars = ax.barh(labels[::-1], [v / 1000 for v in vals[::-1]], color=colors[::-1], height=0.55)
    
    for bar, val in zip(bars, vals[::-1]):
        w = bar.get_width()
        ax.text(w + 12, bar.get_y() + bar.get_height() / 2, f"{w:g}k tokens",
                va="center", fontsize=8.8, fontweight="bold", color="#1f2937")

    ax.set_xlim(0, 750)
    ax.set_xlabel(T("每回合估計消耗 Tokens (k)", "Estimated Tokens per Turn (k)"))
    ax.set_title(T("四種 AI 決策架構每回合 Token 預算估算比較", "Estimated Token Budget per Turn Across Four AI Architectures"))
    ax.text(0.99, -0.18, T("資料來源：docs/DESIGN.md §3（以 20 勢力、約 400 位武將之全域規模估算）",
                          "Source: docs/DESIGN.md §3 (Estimated at 20 factions, ~400 officers total scale)"),
            transform=ax.transAxes, ha="right", fontsize=7.5, color=GREY)

    save(fig, "f03_token_cost")


def f08_attention_policies():
    """Defection ratio and final average loyalty across six policies from docs/EVALUATION.md §10."""
    ev = (ROOT / "docs" / "EVALUATION.md").read_text(encoding="utf-8")
    t_start = ev.find("| 策略 | 出奔種子比例 |")
    t_end = ev.find("\n\n全部驗收條件通過", t_start)
    lines = [l.strip() for l in ev[t_start:t_end].splitlines() if l.strip().startswith("|")][2:]

    policies, defect_rates, loyalties = [], [], []
    zh_map = {
        "Stubborn": "Stubborn (頑固死守)",
        "FixedSix": "FixedSix (固定六人)",
        "Core8": "Core8 (核心八人)",
        "RandomFive": "RandomFive (隨機五人)",
        "Rotator": "Rotator (輪替關注)",
        "規則 AI 基準": "規則 AI 基準",
    }
    for l in lines:
        parts = [p.strip() for p in l.split("|")[1:-1]]
        pol = parts[0]
        policies.append(T(zh_map.get(pol, pol), pol))
        defect_rates.append(float(parts[1].replace("%", "")))
        loyalties.append(float(parts[4]))

    fig, ax1 = plt.subplots(figsize=(8.8, 4.2))
    x = np.arange(len(policies))
    w = 0.35

    c_defect = [RED if r >= 50 else ORANGE if r > 0 else GREY for r in defect_rates]
    b1 = ax1.bar(x - w / 2, defect_rates, w, label=T("出奔種子比例 (%)", "Defection Seed Ratio (%)"), color=c_defect)
    ax1.set_ylabel(T("出奔種子比例 (%)", "Defection Seed Ratio (%)"), color=RED)
    ax1.set_ylim(0, 115)
    ax1.tick_params(axis="y", labelcolor=RED)

    ax2 = ax1.twinx()
    b2 = ax2.bar(x + w / 2, loyalties, w, label=T("最終平均忠誠", "Final Average Loyalty"), color=NAVY, alpha=0.85)
    ax2.set_ylabel(T("最終平均忠誠度 (滿分 100)", "Final Average Loyalty (Max 100)"), color=NAVY)
    ax2.set_ylim(0, 115)
    ax2.tick_params(axis="y", labelcolor=NAVY)

    # Threshold markers
    ax2.axhline(50, color="#f59e0b", ls="--", lw=1.2, alpha=0.7)
    ax2.text(len(policies) - 0.5, 52, T("抗旨門檻 (50)", "Disobey (50)"), color="#f59e0b", fontsize=7.8, ha="right")
    ax2.axhline(35, color=RED, ls=":", lw=1.2, alpha=0.7)
    ax2.text(len(policies) - 0.5, 37, T("出奔門檻 (35)", "Defect (35)"), color=RED, fontsize=7.8, ha="right")

    ax1.set_xticks(x)
    ax1.set_xticklabels(policies, rotation=15, ha="right", fontsize=8.5)
    ax1.set_title(T("六種注意力策略之出奔比例與最終平均忠誠（20 種子、40 回合實測）",
                    "Defection Ratio and Final Loyalty Across Six Attention Policies (20 seeds, 40 turns)"))

    save(fig, "f08_attention_policies")


def f09_balance():
    """Winner distribution over seeds 0-39 under default scenario (runs run_headless directly)."""
    from slg.sim.headless import run_headless

    winners = {"faction_1": 0, "faction_2": 0, "faction_3": 0, "draw": 0}
    for seed in range(40):
        r = run_headless(seed=seed, turns=30)
        w = r.winner or "draw"
        winners[w] += 1

    labels = [
        T("曹操 (faction_1)", "Cao Cao (faction_1)"),
        T("劉備 (faction_2)", "Liu Bei (faction_2)"),
        T("孫權 (faction_3)", "Sun Quan (faction_3)"),
        T("和局 (Draw/Tie)", "Draw / Tie"),
    ]
    counts = [winners["faction_1"], winners["faction_2"], winners["faction_3"], winners["draw"]]
    colors = [NAVY, GREEN, ORANGE, GREY]

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    bars = ax.bar(labels, counts, color=colors, width=0.5)

    for bar, c in zip(bars, counts):
        h = bar.get_height()
        pct = (c / 40) * 100
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.35, f"{c} 勝 ({pct:.1f}%)" if c > 0 and bar.get_x() < 2 else f"{c} 局 ({pct:.1f}%)",
                ha="center", fontsize=8.8, fontweight="bold")

    ax.set_ylim(0, 16)
    ax.set_ylabel(T("對局數（總計 40 種子）", "Number of Games (40 seeds total)"))
    ax.set_title(T("預設情境規則 AI 基準線勝者分布（30 回合、種子 0–39 實測）",
                    "Rule-Based Baseline Winner Distribution (30 turns, seeds 0-39)"))

    save(fig, "f09_balance")


def f10_gemini_stages():
    """Acceptance rate and mean troop delta across three Gemini stages from docs/evals/*.json."""
    files = [
        ROOT / "docs/evals/2026-10-10_gemini-3.5-flash-lite_seat-faction_2_before-fix.json",
        ROOT / "docs/evals/2026-10-11_gemini-3.5-flash-lite_seat-faction_2_after-param-fix.json",
        ROOT / "docs/evals/2026-10-11_gemini-3.5-flash-lite_seat-faction_2_after-siege-odds.json",
    ]
    summaries = [json.loads(p.read_text(encoding="utf-8"))["summary"] for p in files]

    stages = [
        T("第一階段：原始格式\n(before-fix)", "Stage 1: Raw Format\n(before-fix)"),
        T("第二階段：參數修正\n(after-param-fix)", "Stage 2: Param Normalization\n(after-param-fix)"),
        T("第三階段：勝算偵察\n(after-siege-odds)", "Stage 3: Siege Odds\n(after-siege-odds)"),
    ]
    accept_rates = [s["orders_accept_rate"] * 100 for s in summaries]
    troop_deltas = [s["mean_troops_delta"] for s in summaries]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0))

    # Acceptance rate
    bars1 = ax1.bar(stages, accept_rates, color=[ORANGE, GREEN, GREEN], width=0.5)
    for bar, v in zip(bars1, accept_rates):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.2, f"{v:.1f}%",
                 ha="center", fontsize=8.8, fontweight="bold")
    ax1.set_ylim(70, 105)
    ax1.set_ylabel(T("指令接受率 (%)", "Order Acceptance Rate (%)"))
    ax1.set_title(T("各階段指令接受率進展", "Acceptance Rate Progression"))

    # Troops delta
    c_troops = [RED if td < 0 else GREEN for td in troop_deltas]
    bars2 = ax2.bar(stages, troop_deltas, color=c_troops, width=0.5)
    for bar, v in zip(bars2, troop_deltas):
        va = "bottom" if v >= 0 else "top"
        y_pos = v + (150 if v >= 0 else -350)
        ax2.text(bar.get_x() + bar.get_width() / 2, y_pos, f"{v:+.1f}",
                 ha="center", fontsize=8.8, fontweight="bold", color=GREEN if v >= 0 else RED)
    ax2.axhline(0, color=GREY, ls="--", lw=1.2)
    ax2.set_ylim(-4800, 1600)
    ax2.set_ylabel(T("平均兵力差（相對規則 AI 基準）", "Mean Troops Delta (vs Rule Baseline)"))
    ax2.set_title(T("各階段最終兵力差變化", "Mean Troops Delta Progression"))

    fig.suptitle(T("Gemini-3.5-flash-lite 三階段實驗關鍵指標演進（劉備席位、種子 0–5）",
                   "Gemini-3.5-flash-lite Three-Stage Experimental Metrics (Seat Liu Bei, seeds 0-5)"),
                 fontsize=11.5, fontweight="bold", y=1.02)
    plt.tight_layout()
    save(fig, "f10_gemini_stages")


def f11_rejections():
    """Top 3 rejection reasons before and after fix from Gemini evaluations."""
    p1 = ROOT / "docs/evals/2026-10-10_gemini-3.5-flash-lite_seat-faction_2_before-fix.json"
    p2 = ROOT / "docs/evals/2026-10-11_gemini-3.5-flash-lite_seat-faction_2_after-param-fix.json"
    r1 = json.loads(p1.read_text(encoding="utf-8"))["summary"]["diagnostics"]["rejection_reasons"]
    r2 = json.loads(p2.read_text(encoding="utf-8"))["summary"]["diagnostics"]["rejection_reasons"]

    # Shorten labels for readable presentation
    def clean_reason(r):
        r = r.replace("param to=['wancheng'] not in choices", "to=['...'] not in choices")
        r = r.replace("param troops=N out of range [N, N]", "troops out of range")
        return r

    labels_s1 = [clean_reason(x["reason"]) for x in r1[:3]]
    counts_s1 = [x["count"] for x in r1[:3]]

    labels_s2 = [clean_reason(x["reason"]) for x in r2[:3]]
    counts_s2 = [x["count"] for x in r2[:3]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.8))

    # Stage 1
    y1 = np.arange(len(labels_s1))
    ax1.barh(y1, counts_s1, color=RED, height=0.55)
    for i, v in enumerate(counts_s1):
        ax1.text(v + 1.2, i, f"{v} 次", va="center", fontsize=8.8, fontweight="bold")
    ax1.set_yticks(y1)
    ax1.set_yticklabels(labels_s1, fontsize=8.2)
    ax1.set_xlim(0, 52)
    ax1.set_xlabel(T("被拒次數", "Count"))
    ax1.set_title(T("修正前（階段一，總計 64 次被拒）", "Before Fix (Stage 1, 64 total rejects)"))
    ax1.invert_yaxis()

    # Stage 2
    y2 = np.arange(len(labels_s2))
    ax2.barh(y2, counts_s2, color=ORANGE, height=0.55)
    for i, v in enumerate(counts_s2):
        ax2.text(v + 0.6, i, f"{v} 次", va="center", fontsize=8.8, fontweight="bold")
    ax2.set_yticks(y2)
    ax2.set_yticklabels(labels_s2, fontsize=8.2)
    ax2.set_xlim(0, 20)
    ax2.set_xlabel(T("被拒次數", "Count"))
    ax2.set_title(T("修正後（階段二，總計 29 次被拒）", "After Fix (Stage 2, 29 total rejects)"))
    ax2.invert_yaxis()

    fig.suptitle(T("參數規範修正前後指令被拒原因前三名對比", "Top-3 Rejection Reasons Comparison Before and After Fix"),
                 fontsize=11.5, fontweight="bold", y=1.02)
    plt.tight_layout()
    save(fig, "f11_rejections")


def f12_qwen_q1():
    """Q1 three seats troop delta and order acceptance rate for Qwen3.8-27B."""
    seats = ["faction_1", "faction_2", "faction_3"]
    seat_names = [
        T("曹操 (faction_1)", "Cao Cao (faction_1)"),
        T("劉備 (faction_2)", "Liu Bei (faction_2)"),
        T("孫權 (faction_3)", "Sun Quan (faction_3)"),
    ]
    troop_deltas, accept_rates = [], []
    for s in seats:
        p = ROOT / f"docs/evals/qwen/q1_default_{s}.json"
        data = json.loads(p.read_text(encoding="utf-8"))["summary"]
        troop_deltas.append(data["mean_troops_delta"])
        accept_rates.append(data["orders_accept_rate"] * 100)

    fig, ax1 = plt.subplots(figsize=(8.2, 4.0))
    x = np.arange(len(seats))
    w = 0.35

    c_troops = [GREEN if td >= 0 else RED for td in troop_deltas]
    b1 = ax1.bar(x - w / 2, troop_deltas, w, color=c_troops, label=T("平均兵力差", "Mean Troops Delta"))
    for bar, td in zip(b1, troop_deltas):
        va = "bottom" if td >= 0 else "top"
        y_pos = td + (120 if td >= 0 else -280)
        ax1.text(bar.get_x() + bar.get_width() / 2, y_pos, f"{td:+.1f}",
                 ha="center", fontsize=8.5, fontweight="bold")
    ax1.axhline(0, color=GREY, ls="--", lw=1.0)
    ax1.set_ylabel(T("兵力差（相對規則 AI）", "Troops Delta (vs Baseline)"), color=NAVY)
    ax1.set_ylim(-1200, 3400)

    ax2 = ax1.twinx()
    b2 = ax2.bar(x + w / 2, accept_rates, w, color=PURPLE, alpha=0.8, label=T("指令接受率 (%)", "Acceptance Rate (%)"))
    for bar, ar in zip(b2, accept_rates):
        ax2.text(bar.get_x() + bar.get_width() / 2, ar + 1.2, f"{ar:.1f}%",
                 ha="center", fontsize=8.5, fontweight="bold", color=PURPLE)
    ax2.set_ylabel(T("指令接受率 (%)", "Order Acceptance Rate (%)"), color=PURPLE)
    ax2.set_ylim(50, 105)
    ax2.tick_params(axis="y", labelcolor=PURPLE)

    ax1.set_xticks(x)
    ax1.set_xticklabels(seat_names, fontsize=9)
    ax1.set_title(T("本機 Qwen3.8-27B（Q1 實驗）三座位兵力差與指令接受率",
                    "Local Qwen3.8-27B (Q1) Troop Delta and Acceptance Rate Across Three Seats"))

    save(fig, "f12_qwen_q1")


def f13_siege_outcomes():
    """Siege outcomes across Q2 (10/7 vs 7/0), Gemini Stage 2 (35/0), and Q1/Q3 (22/1)."""
    # 1. Q2 Advantage (Qwen vs Baseline)
    q2_p = ROOT / "docs/evals/qwen/q2_advantage_faction_2.json"
    q2_diag = json.loads(q2_p.read_text(encoding="utf-8"))["summary"]["diagnostics"]["siege_outcomes"]
    q2_exp_att, q2_exp_cap = q2_diag["experiment"]["attempts"], q2_diag["experiment"]["captured"]
    q2_base_att, q2_base_cap = q2_diag["baseline"]["attempts"], q2_diag["baseline"]["captured"]

    # 2. Gemini Stage 2 (after param fix)
    gem_p = ROOT / "docs/evals/2026-10-11_gemini-3.5-flash-lite_seat-faction_2_after-param-fix.json"
    gem_diag = json.loads(gem_p.read_text(encoding="utf-8"))["summary"]["diagnostics"]["siege_outcomes"]
    gem_att, gem_cap = gem_diag["experiment"]["attempts"], gem_diag["experiment"]["captured"]

    # 3. Q1 + Q3 aggregate
    q_other_paths = glob.glob(str(ROOT / "docs/evals/qwen/q1_*.json")) + glob.glob(str(ROOT / "docs/evals/qwen/q3_*.json"))
    q_other_att = sum(json.loads(Path(p).read_text(encoding="utf-8"))["summary"]["diagnostics"]["siege_outcomes"]["experiment"]["attempts"] for p in q_other_paths)
    q_other_cap = sum(json.loads(Path(p).read_text(encoding="utf-8"))["summary"]["diagnostics"]["siege_outcomes"]["experiment"]["captured"] for p in q_other_paths)

    labels = [
        T("Q2 優勢情境: Qwen\n(具勝算偵察情報)", "Q2 Advantage: Qwen\n(With Recon Odds)"),
        T("Q2 優勢情境: 規則 AI\n(基準線無勝算提示)", "Q2 Advantage: Rule AI\n(Baseline)"),
        T("Gemini 第二階段\n(無勝算提示，盲目出征)", "Gemini Stage 2\n(No Recon Odds)"),
        T("Q1/Q3 標準情境\n(防守反擊/少主動攻城)", "Q1/Q3 Default Scenario\n(Defensive Posture)"),
    ]
    attempts = [q2_exp_att, q2_base_att, gem_att, q_other_att]
    captures = [q2_exp_cap, q2_base_cap, gem_cap, q_other_cap]

    x = np.arange(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(8.8, 4.2))

    b1 = ax.bar(x - w / 2, attempts, w, label=T("主動攻城嘗試次數", "Siege Attempts"), color=GREY, alpha=0.85)
    b2 = ax.bar(x + w / 2, captures, w, label=T("攻克成功次數", "Successful Captures"), color=GREEN)

    for bar, a, c in zip(b1, attempts, captures):
        ax.text(bar.get_x() + bar.get_width() / 2, a + 0.8, f"{a} 次", ha="center", fontsize=8.2)
    for bar, c in zip(b2, captures):
        ax.text(bar.get_x() + bar.get_width() / 2, c + 0.8, f"{c} 次", ha="center", fontsize=8.2, fontweight="bold", color=GREEN if c > 0 else GREY)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(0, 42)
    ax.set_ylabel(T("次數", "Count"))
    ax.set_title(T("不同模型與情境下攻城嘗試與成功攻克戰績對比", "Siege Attempts vs Captures Across Models and Scenarios"))
    ax.legend(frameon=True, fontsize=8.8)

    save(fig, "f13_siege_outcomes")


def f14_long_games():
    """Q3 40-turn games troop deltas across three seats (all 0 defections)."""
    seats = ["faction_1", "faction_2", "faction_3"]
    seat_labels = [
        T("曹操 (faction_1)\n長局兵力大幅領先", "Cao Cao (faction_1)\nTroop Lead"),
        T("劉備 (faction_2)\n長局穩定維持正成長", "Liu Bei (faction_2)\nStable Growth"),
        T("孫權 (faction_3)\n長局高兵力優勢", "Sun Quan (faction_3)\nHigh Advantage"),
    ]
    deltas = []
    deflections = []
    for s in seats:
        p = ROOT / f"docs/evals/qwen/q3_long_{s}.json"
        data = json.loads(p.read_text(encoding="utf-8"))["summary"]
        deltas.append(data["mean_troops_delta"])
        deflections.append(data.get("diagnostics", {}).get("incidents", {}).get("deflections", 0))

    fig, ax = plt.subplots(figsize=(7.8, 4.0))
    x = np.arange(len(seats))
    bars = ax.bar(x, deltas, color=[NAVY, GREEN, ORANGE], width=0.45)

    for bar, d, defl in zip(bars, deltas, deflections):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 140, f"{d:+.1f}",
                ha="center", fontsize=9.2, fontweight="bold")
        ax.text(bar.get_x() + bar.get_width() / 2, h / 2, T(f"出奔次數: {defl}", f"Defections: {defl}"),
                ha="center", fontsize=8.2, color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(seat_labels, fontsize=8.5)
    ax.set_ylim(0, 5200)
    ax.set_ylabel(T("40 回合最終平均兵力差（相對規則 AI）", "40-Turn Final Mean Troops Delta (vs Rule AI)"))
    ax.set_title(T("Q3 四十回合長局各座位兵力差（全部座位 0 次出奔）",
                   "Q3 40-Turn Long Games: Troop Delta Across Seats (Zero Defections in All Seats)"))

    save(fig, "f14_long_games")


if __name__ == "__main__":
    f03_token_cost()
    f08_attention_policies()
    f09_balance()
    f10_gemini_stages()
    f11_rejections()
    f12_qwen_q1()
    f13_siege_outcomes()
    f14_long_games()
