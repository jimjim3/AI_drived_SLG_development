"""Concept diagrams for the textbook (no experimental data required)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fig_common import (
    CYCLE, GREEN, GREY, LIGHT, NAVY, ORANGE, PURPLE, RED, T,
    arrow, box, plt, save,
)
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle


def f01_architecture():
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.0, 5.0)
    ax.axis("off")

    # Title
    ax.set_title(T("分層 AI 決策架構與資料流", "Hierarchical AI Decision Architecture and Dataflow"))

    # Boxes
    box(ax, 0.4, 3.2, 2.2, 1.2, T("遊戲世界狀態\nGameState (不可變)", "World State\nGameState (Immutable)"), fc=LIGHT, ec=NAVY, bold=True, fs=9.2)
    box(ax, 3.4, 3.2, 2.4, 1.2, T("勢力視野建構\nFactionView (迷霧/名單)", "View Builder\nFactionView (Fog/Cast)"), fc=LIGHT, ec=NAVY, fs=9.2)
    box(ax, 6.6, 3.2, 2.8, 1.2, T("勢力決策代理\nFactionAgent (LLM/規則)", "Decision Agent\nFactionAgent (LLM/Rule)"), fc="#fff3e0", ec=ORANGE, bold=True, fs=9.2)

    box(ax, 6.6, 0.9, 2.8, 1.2, T("勢力計畫\nFactionPlan (指令+史書)", "Faction Plan\nFactionPlan (Orders+Cast)"), fc="#fff3e0", ec=ORANGE, fs=9.2)
    box(ax, 3.4, 0.9, 2.4, 1.2, T("引擎二重驗證\nValidation (安全網)", "Engine Validation\nValidation (Safety Net)"), fc="#d9eadf", ec=GREEN, bold=True, fs=9.2)
    box(ax, 0.4, 0.9, 2.2, 1.2, T("回合結算\nResolution (執行+委任)", "Turn Resolution\nResolution (Exec+Delegate)"), fc="#d9eadf", ec=GREEN, fs=9.2)

    # Replay branch
    box(ax, 0.4, -0.6, 2.2, 0.8, T("確定性日誌 TurnLog\n100% 重播還原", "Deterministic TurnLog\n100% State Replay"), fc="#f3e5f5", ec=PURPLE, fs=9.0)

    # Arrows
    arrow(ax, 2.6, 3.8, 3.4, 3.8, color=NAVY)
    arrow(ax, 5.8, 3.8, 6.6, 3.8, color=NAVY)
    arrow(ax, 8.0, 3.2, 8.0, 2.1, color=ORANGE)
    arrow(ax, 6.6, 1.5, 5.8, 1.5, color=ORANGE)
    arrow(ax, 3.4, 1.5, 2.6, 1.5, color=GREEN)
    arrow(ax, 1.5, 2.1, 1.5, 3.2, color=GREEN)
    arrow(ax, 1.5, 0.9, 1.5, 0.2, color=PURPLE)

    ax.text(5.0, -0.4, T("確定性閉環：每回合狀態轉移由單一種子保證完全可重現", "Deterministic loop: every state transition is 100% reproducible with single seed"),
            ha="center", fontsize=9.0, color=GREY)

    save(fig, "f01_architecture")


def f02_map():
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 8.5)
    ax.axis("off")
    ax.set_title(T("三勢力九城地圖鄰接關係與初始配置", "Three Factions, Nine Cities Adjacency Graph and Initial Setup"))

    # Cities: id: (x, y, name_zh, name_en, faction, faction_zh, officers, troops)
    nodes = {
        "hanzhong": (1.4, 2.6, "漢中", "Hanzhong", "faction_2", "劉備", 4, 700),
        "wancheng": (3.4, 3.8, "宛城", "Wancheng", "faction_2", "劉備", 4, 700),
        "luoyang": (4.2, 6.4, "洛陽", "Luoyang", "faction_2", "劉備", 6, 1100),
        "chenliu": (7.2, 7.2, "陳留", "Chenliu", "faction_1", "曹操", 4, 800),
        "xuchang": (7.0, 4.8, "許昌", "Xuchang", "faction_1", "曹操", 6, 1400),
        "xiangyang": (5.6, 2.2, "襄陽", "Xiangyang", "faction_1", "曹操", 4, 1200),
        "jianye": (8.8, 3.4, "建業", "Jianye", "faction_3", "孫權", 6, 1200),
        "wujun": (9.8, 2.1, "吳郡", "Wujun", "faction_3", "孫權", 4, 800),
        "kuaiji": (9.8, 0.7, "會稽", "Kuaiji", "faction_3", "孫權", 4, 800),
    }

    edges = [
        ("hanzhong", "wancheng"),
        ("wancheng", "luoyang"),
        ("luoyang", "xuchang"),
        ("luoyang", "xiangyang"),
        ("chenliu", "xuchang"),
        ("xuchang", "xiangyang"),
        ("xiangyang", "jianye"),
        ("jianye", "wujun"),
        ("wujun", "kuaiji"),
    ]

    # Draw edges
    for u, v in edges:
        x0, y0 = nodes[u][0], nodes[u][1]
        x1, y1 = nodes[v][0], nodes[v][1]
        ax.plot([x0, x1], [y0, y1], color="#9ca3af", lw=2.2, zorder=1)

    colors = {
        "faction_1": (NAVY, "#e8eef5"),
        "faction_2": (GREEN, "#e8f5e9"),
        "faction_3": (ORANGE, "#fff3e0"),
    }

    # Draw nodes
    for cid, (x, y, n_zh, n_en, fid, f_zh, offs, trps) in nodes.items():
        ec, fc = colors[fid]
        w, h = 2.05, 1.05
        box(ax, x - w / 2, y - h / 2, w, h,
            f"{T(n_zh, n_en)} ({T(f_zh, fid)})\n{T(f'{offs}將 · {trps}兵', f'{offs} off · {trps} trp')}",
            fc=fc, ec=ec, fs=9.0, bold=True, tc=ec)

    # Legend
    ax.plot([], [], color=NAVY, label=T("曹操勢力 (faction_1: 許昌/陳留/襄陽，共14將)", "Cao Cao (faction_1: 14 officers)"))
    ax.plot([], [], color=GREEN, label=T("劉備勢力 (faction_2: 洛陽/宛城/漢中，共14將)", "Liu Bei (faction_2: 14 officers)"))
    ax.plot([], [], color=ORANGE, label=T("孫權勢力 (faction_3: 建業/吳郡/會稽，共14將)", "Sun Quan (faction_3: 14 officers)"))
    ax.legend(loc="upper left", frameon=True, fontsize=9.0)

    save(fig, "f02_map")


def f04_turn_sequence():
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.5)
    ax.axis("off")
    ax.set_title(T("單一回合時序執行流程（Turn Sequence）", "Single-Turn Execution Sequence"))

    steps = [
        (0.5, 2.8, 1.9, 1.4, T("1. 資源結算\n城池金/糧收入\n部隊軍糧消耗", "1. Resource Step\nCity Gold/Food\nTroop Food Drain"), LIGHT, NAVY),
        (2.8, 2.8, 1.9, 1.4, T("2. 行動順序\nrng.shuffle\n隨機排定勢力序", "2. Order Shuffle\nrng.shuffle\nRandom Faction Order"), LIGHT, NAVY),
        (5.1, 2.8, 2.3, 1.4, T("3. 勢力循環決策\n生成 FactionView\nLLM / 代理產出 Plan", "3. Faction Loop\nGenerate FactionView\nAgent outputs Plan"), "#fff3e0", ORANGE),
        (7.8, 2.8, 2.7, 1.4, T("4. 指令驗證與結算\n逐條驗證 orders\n衝突與攻城結算", "4. Verification\nValidate each order\nSiege & Battle resolve"), "#d9eadf", GREEN),
        (5.1, 0.6, 2.3, 1.3, T("5. 未點名自動委任\n其餘存活武將\n由規則 AI 自動執行", "5. Auto Delegation\nRemaining officers\ndelegated to Rule AI"), LIGHT, NAVY),
        (1.7, 0.6, 2.7, 1.3, T("6. 回合結束心理結算\n冷落累積、毛遂自薦\n低忠誠抗旨與出奔", "6. End of Turn\nNeglect penalty\nPetition & Defection"), "#fde7d0", RED),
    ]

    for x, y, w, h, text, fc, ec in steps:
        box(ax, x, y, w, h, text, fc=fc, ec=ec, fs=9.0, bold=True)

    # Connectors
    arrow(ax, 2.4, 3.5, 2.8, 3.5, color=NAVY)
    arrow(ax, 4.7, 3.5, 5.1, 3.5, color=NAVY)
    arrow(ax, 7.4, 3.5, 7.8, 3.5, color=ORANGE)
    ax.plot([9.15, 9.15], [2.8, 1.25], color=GREEN, lw=1.4)
    arrow(ax, 9.15, 1.25, 7.4, 1.25, color=GREEN)
    arrow(ax, 5.1, 1.25, 4.4, 1.25, color=NAVY)

    save(fig, "f04_turn_sequence")


def f05_view_blocks():
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title(T("勢力視野（FactionView）六大組成區塊", "The Six Structural Blocks of FactionView"))

    blocks = [
        (0.5, 3.2, 2.7, 2.2, T("cities（己方城池）\n· 所屬城池名與兵糧金\n· 農業/商業/城防狀態\n· 駐紮武將名單索引", "cities (Owned)\n· City IDs & resources\n· Agri/Comm/Defense\n· Stationed officer list"), LIGHT, NAVY),
        (3.6, 3.2, 2.7, 2.2, T("frontier（前線情資）\n· 戰爭迷霧過濾\n· 僅揭露相鄰敵城\n· 敵城兵力與防禦概況", "frontier (Frontier)\n· Fog of war filter\n· Adjacent enemy cities\n· Visible enemy troops"), "#e0f2fe", NAVY),
        (6.7, 3.2, 2.8, 2.2, T("cast（聚光名單）\n· 上限 6 人詳細數據\n· 統帥/武力/智力/政治\n· 忠誠度與受冷落回合數", "cast (Spotlight)\n· Top 6 detailed officers\n· Stats (war/pol/etc)\n· Loyalty & neglect count"), "#fff3e0", ORANGE),
        (0.5, 0.5, 2.7, 2.2, T("roster（其餘名冊）\n· 未點名武將輕量索引\n· 每人僅一行標記所在\n· 供君主下一回合點名", "roster (Brief Roster)\n· Compressed one-line list\n· Name & current city\n· Available for next_cast"), LIGHT, GREY),
        (3.6, 0.5, 2.7, 2.2, T("events（突發事件）\n· 毛遂自薦事件登載\n· 戰報與新登用消息\n· 強制插入出場名單", "events (Incidents)\n· Self-petition notices\n· Battle & recruit news\n· Forced cast insertions"), "#fde7d0", RED),
        (6.7, 0.5, 2.8, 2.2, T("feedback（執行反饋）\n· 上回合指令被拒原因\n· 參數越界/非法動作提示\n· 指導 LLM 調整下回合策略", "feedback (Feedback)\n· Rejection reasons\n· Out-of-bounds hints\n· Corrective signals"), "#d9eadf", GREEN),
    ]

    for x, y, w, h, text, fc, ec in blocks:
        box(ax, x, y, w, h, text, fc=fc, ec=ec, fs=9.0, bold=False)

    save(fig, "f05_view_blocks")


def f06_safety_net():
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.8, 5.0)
    ax.axis("off")
    ax.set_title(T("引擎驗證安全網流程（Safety Net Pipeline）", "Engine Validation Safety Net Pipeline"))

    box(ax, 0.5, 3.2, 2.2, 1.1, T("合法行動生成\ngenerate_legal_actions", "Legal Actions\ngenerate_legal_actions"), fc=LIGHT, ec=NAVY, bold=True, fs=9.0)
    box(ax, 3.2, 3.2, 2.0, 1.1, T("LLM 產出計畫\nparse_plan", "LLM Plan\nparse_plan"), fc="#fff3e0", ec=ORANGE, fs=9.0)
    box(ax, 5.8, 3.2, 1.8, 1.1, T("引擎二重驗證\n合法？", "Validation\nLegal?"), fc="#d9eadf", ec=GREEN, bold=True, fs=9.0)
    box(ax, 8.2, 3.2, 1.4, 1.1, T("執行決策\nresolve", "Execute\nresolve"), fc="#d9eadf", ec=GREEN, fs=9.0)

    box(ax, 5.8, 1.4, 1.8, 1.1, T("重試預算\n> 0 次？", "Retry Budget\n> 0?"), fc=LIGHT, ec=ORANGE, fs=9.0)
    box(ax, 3.2, 1.4, 2.0, 1.1, T("帶反饋重試\nRetry with feedback", "Retry\nwith feedback"), fc="#fff3e0", ec=ORANGE, fs=9.0)
    box(ax, 8.0, 1.4, 1.6, 1.1, T("規則 AI 兜底\nRule-based", "Rule-Based\nFallback"), fc="#fde7d0", ec=RED, fs=9.0)
    box(ax, 8.0, -0.4, 1.6, 1.0, T("保底休息\nrest（必合法）", "Guaranteed\nrest (always legal)"), fc=LIGHT, ec=GREY, fs=9.0)

    # Connections
    arrow(ax, 2.7, 3.75, 3.2, 3.75, color=NAVY)
    arrow(ax, 5.2, 3.75, 5.8, 3.75, color=ORANGE)
    arrow(ax, 7.6, 3.75, 8.2, 3.75, color=GREEN)
    ax.text(7.9, 3.95, T("是 (Yes)", "Yes"), fontsize=9.0, color=GREEN, ha="center")

    arrow(ax, 6.7, 3.2, 6.7, 2.5, color=RED)
    ax.text(6.9, 2.85, T("否 (No)", "No"), fontsize=9.0, color=RED)

    arrow(ax, 5.8, 1.95, 5.2, 1.95, color=ORANGE)
    ax.text(5.5, 2.15, T("是", "Yes"), fontsize=9.0, color=ORANGE)
    arrow(ax, 4.2, 2.5, 4.2, 3.2, color=ORANGE)

    arrow(ax, 7.6, 1.95, 8.0, 1.95, color=RED)
    ax.text(7.8, 2.15, T("否", "No"), fontsize=9.0, color=RED)
    arrow(ax, 8.8, 1.4, 8.8, 0.6, color=GREY)

    save(fig, "f06_safety_net")


def f07_loyalty_states():
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")
    ax.set_title(T("武將忠誠與冷落狀態轉移圖", "Officer Loyalty and Neglect State Transitions"))

    box(ax, 0.4, 2.6, 2.2, 1.4, T("正常在朝\n· 被列入 cast 聚光燈\n· 冷落計數 = 0\n· 忠誠度每回合 +1", "Spotlight State\n· Listed in cast\n· neglect_count = 0\n· loyalty += 1"), fc="#d9eadf", ec=GREEN, bold=True, fs=9.0)
    box(ax, 4.0, 2.6, 2.4, 1.4, T("冷落累積\n· 未點名持續累積\n· 達門檻（≥4 回合）\n· 忠誠每回合 -1", "Neglect Accumulation\n· Unnamed count +1\n· >= NEGLECT_PENALTY\n· loyalty -= 1"), fc="#fff3e0", ec=ORANGE, bold=True, fs=9.0)
    box(ax, 7.4, 2.6, 2.2, 1.4, T("毛遂自薦\n· 冷落≥4 且忠誠<80\n· 引擎強制插入 cast\n· 給予君主補救機會", "Self-Petition\n· neglect>=4 & loy<80\n· Forced into cast\n· Monarch second chance"), fc="#e0f2fe", ec=NAVY, bold=True, fs=9.0)

    box(ax, 4.0, 0.4, 2.4, 1.3, T("抗旨判定\n· 忠誠 < DISOBEY(50)\n· 執行指令時偏離\n· 自動轉為休息或違令", "Disobedience\n· loyalty < DISOBEY (50)\n· Action deviation roll\n· Fails to obey orders"), fc="#fde7d0", ec=RED, fs=9.0)
    box(ax, 7.4, 0.4, 2.2, 1.3, T("出奔叛逃\n· 忠誠 < DEFECT(35)\n· 所在城與敵城相鄰\n· 投奔鄰近敵對勢力", "Defection\n· loyalty < DEFECT (35)\n· City borders enemy\n· Defects to enemy"), fc="#ffebee", ec=RED, bold=True, fs=9.0)

    # Transitions
    arrow(ax, 2.6, 3.5, 4.0, 3.5, color=ORANGE)
    ax.text(3.3, 3.7, T("連續未被點名", "Unattended"), fontsize=9.0, ha="center")

    arrow(ax, 4.0, 3.1, 2.6, 3.1, color=GREEN)
    ax.text(3.3, 2.75, T("重新點名關注", "Named in cast"), fontsize=9.0, ha="center")

    arrow(ax, 6.4, 3.3, 7.4, 3.3, color=NAVY)
    ax.text(6.9, 3.5, T("觸發自薦", "Petition"), fontsize=9.0, ha="center")

    arrow(ax, 5.2, 2.6, 5.2, 1.7, color=RED)
    ax.text(5.6, 2.15, T("忠誠 < 50", "loyalty < 50"), fontsize=9.0)

    arrow(ax, 6.4, 1.05, 7.4, 1.05, color=RED)
    ax.text(6.9, 1.25, T("忠誠 < 35", "loyalty < 35"), fontsize=9.0, ha="center")

    save(fig, "f07_loyalty_states")


def f15_orchestration():
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")
    ax.set_title(T("主管 AI 與外包 Worker 協調架構與驗收迴圈", "Orchestration and Verification Loop: Supervisor AI and Workers"))

    box(ax, 3.0, 3.6, 4.0, 1.1, T("主管 AI / 總編輯\n規格制定 · 任務拆解 · 驗收標準", "Supervisor AI / Editor-in-Chief\nSpec Authoring · Task Decomposition"), fc=LIGHT, ec=NAVY, bold=True, fs=9.2)

    box(ax, 0.4, 2.0, 2.6, 1.0, T("agy（雲端 Worker）\n高複雜度架構與重構實作", "agy (Cloud Worker)\nComplex Architecture & Refactors"), fc="#fff3e0", ec=ORANGE, fs=9.0)
    box(ax, 3.6, 2.0, 2.8, 1.0, T("Qwen（本機 27B Worker）\n參數調校 · 大規模離線模擬", "Qwen (Local 27B Worker)\nHyperparam Tuning · Simulation"), fc="#d9eadf", ec=GREEN, fs=9.0)
    box(ax, 7.0, 2.0, 2.6, 1.0, T("nim-staff（獨立審計）\n二審意見 · 跨域總結審查", "nim-staff (Audit)\nSecond Opinion · Audit Review"), fc="#e0f2fe", ec=PURPLE, fs=9.0)

    box(ax, 1.5, 0.2, 7.0, 1.2, T("四重對抗驗收迴圈（不採信 Worker 自述）\n① 單元測試全過 (338 tests)　② 結算回歸驗證（種子 0-9 逐局一致）\n③ 突變測試驗證測試集鑑別力　④ 斷路器與額度熔斷保護",
                                   "Quad-Layer Adversarial Verification (Never Trust Self-Reports)\n① Unittests Pass (338 tests)　② Deterministic Replay Match\n③ Mutation Testing Kill-Rate　④ Circuit Breaker Protection"),
        fc="#ffebee", ec=RED, bold=True, fs=9.0)

    arrow(ax, 4.2, 3.6, 2.0, 3.0, color=ORANGE)
    arrow(ax, 5.0, 3.6, 5.0, 3.0, color=GREEN)
    arrow(ax, 5.8, 3.6, 8.0, 3.0, color=PURPLE)

    arrow(ax, 1.7, 2.0, 2.5, 1.4, color=RED)
    arrow(ax, 5.0, 2.0, 5.0, 1.4, color=RED)
    arrow(ax, 8.3, 2.0, 7.5, 1.4, color=RED)

    save(fig, "f15_orchestration")


def f16_roadmap():
    fig, ax = plt.subplots(figsize=(9.4, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title(T("專案演進里程碑與研究路線圖", "Project Milestones and Research Roadmap"))

    cols = [
        (0.4, T("已完成里程碑", "Completed Milestones"), GREEN, [
            T("· 核心引擎與規則結算\n  (338 項測試全數通過)", "· Engine & Rules v2\n  (338 tests pass)"),
            T("· 勢力敘事與聚光機制\n  (CAST_LIMIT=6 人)", "· Faction Narration\n  (CAST_LIMIT=6)"),
            T("· 1296 組合忠誠門檻調校\n  (離線網格搜尋收斂)", "· 1296-Grid Attention\n  Sweep Completed"),
            T("· Gemini 3 階段評測與\n  Qwen Q1-Q4 大規模實驗", "· Gemini 3 Stages &\n  Qwen Q1-Q4 Evals"),
            T("· 確定性重播與診斷評測", "· Deterministic Replay\n  & Diagnostics Suite"),
        ]),
        (3.6, T("近期工程規劃", "Near-Term Engineering"), ORANGE, [
            T("· Qwen 40 回合長局調參複驗", "· Qwen 40-Turn Long-Game\n  Re-eval"),
            T("· 視圖增加各城金幣預算\n  (降低 20% 被拒率)", "· City Gold Budget in View\n  (Cut 20% Rejections)"),
            T("· 地理位置優勢平衡\n  重啟自我對弈測試", "· Seat Balance &\n  Self-Play Restart"),
            T("· 攻城損耗歸因診斷規則細化", "· Enhanced Siege Loss\n  Attribution Rules"),
        ]),
        (6.8, T("遠期研究展望", "Long-Term Horizons"), NAVY, [
            T("· 人類玩家代理介面\n  (FactionAgent 封裝)", "· Human Player UI\n  (FactionAgent Wrap)"),
            T("· 擴大評測種子數與\n  置信區間統計檢定", "· Expand Eval Seeds &\n  Confidence Intervals"),
            T("· gemini-3.5-flash\n  高階模型對比基準", "· Benchmark Against\n  gemini-3.5-flash"),
            T("· 多勢力長程歷史史書生成評估", "· Multi-Faction History\n  Generation Eval"),
        ]),
    ]

    for x, header, color, items in cols:
        box(ax, x, 4.8, 2.8, 0.7, header, fc=color, ec=color, tc="white", bold=True, fs=9.5)
        box(ax, x, 0.4, 2.8, 4.2, "\n\n".join(items), fc="white", ec=color, tc="#1f2937", fs=9.0)

    arrow(ax, 3.2, 5.15, 3.6, 5.15, color=GREY)
    arrow(ax, 6.4, 5.15, 6.8, 5.15, color=GREY)

    save(fig, "f16_roadmap")


if __name__ == "__main__":
    f01_architecture()
    f02_map()
    f04_turn_sequence()
    f05_view_blocks()
    f06_safety_net()
    f07_loyalty_states()
    f15_orchestration()
    f16_roadmap()
