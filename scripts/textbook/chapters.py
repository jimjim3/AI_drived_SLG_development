"""Chapter specifications, figure mappings, and outline for the textbook."""
import pathlib
from book import ROOT

CHAPTERS = []


def chapter(**kw):
    CHAPTERS.append(kw)
    return kw


# ==============================================================================
# 第一篇　動機與基礎
# ==============================================================================

chapter(
    n=1, num="1", slug="motivation",
    title="動機：為什麼讓 LLM 當君主",
    title_en="Motivation: Why Let LLMs Be Monarchs",
    part="第一篇　動機與基礎",
    sources=[ROOT / "docs/DESIGN.md", ROOT / "docs/PRIOR_ART.md", ROOT / "README.md"],
    must_include=[
        "每位武將每回合各呼叫一次／每位武將每回合都問",
        "630,000／63 萬 tokens／~630k",
        "勢力敘事",
        "vox-deorum",
        "CivAgent",
        "CivRealm",
        "規則與機制不受著作權保護／規則與機制：著作權不保護／著作權不保護",
        "《三國演義》公有領域／《三國演義》原文、陳壽《三國志》：公有領域／公有領域",
    ],
    facts=[
        "每位武將每回合都問", "勢力敘事", "vox-deorum", "CivAgent", "CivRealm",
        "著作權不保護", "公有領域",
    ],
    figures=[
        ("f01_architecture", "分層 AI 決策架構與資料流：從遊戲狀態到確定性重播", "1.2"),
        ("f03_token_cost", "四種決策架構之每回合 Token 預算估算比較", "1.4"),
    ],
    length=(3500, 6000),
    position="全書開篇：剖析傳統全 LLM 代理架構的 Token 爆炸困境，提出「君主分層決策」的核心構想與法律/文獻基礎。",
    outline="""1.1 全 LLM 代理的虛妄：若讓「每位武將每回合都問」，在 400 人規模下每回合消耗高達 ~630k tokens，一局 300 回合耗費上億 tokens，延遲與成本皆無法承受。
1.2 相關研究借鏡：分析 CivAgent、CivRealm 等遊戲 AI 嘗試，以及 vox-deorum 等神權代理架構的得失與邊界。
1.3 勢力敘事與層級切分：君主決定戰略方向，中層執行配置，基層事件驅動；以「勢力敘事模式」將全勢力壓縮為每回合單次呼叫。
1.4 智慧財產與公開領域邊界：遊戲規則與機制不受著作權保護（idea/expression 二分法），《三國演義》原文與陳壽《三國志》為公有領域，為獨立研發提供合法基石。
1.5 本書結構與章節地圖：從世界規則、注意力經濟到安全網與實證數據。""",
    notes="注意區分全呼叫與分層呼叫的成本差距，強調法律與公有領域依據。",
)

chapter(
    n=2, num="2", slug="world_rules",
    title="遊戲世界與規則",
    title_en="Game World and Core Rules",
    part="第一篇　動機與基礎",
    sources=[
        ROOT / "src/slg/schema.py",
        ROOT / "src/slg/engine/initial_state.py",
        ROOT / "src/slg/engine/resolution.py",
        ROOT / "src/slg/engine/game.py",
        ROOT / "README.md",
    ],
    must_include=[
        "9 城／nine cities",
        "42 位武將／forty-two officers",
        "每勢力 14 位／14 officers",
        "commerce // GOLD_INCOME_DIV",
        "agriculture // 4",
        "troops // 10",
        "0.8, 1.2",
        "(50 + politics)",
        "MIN_SIEGE_TROOPS",
        "字典序／(城數, 總兵力)／(城池數, 總兵力)",
    ],
    facts=[
        "commerce // GOLD_INCOME_DIV", "agriculture // 4", "troops // 10",
        "0.8, 1.2", "(50 + politics)", "MIN_SIEGE_TROOPS",
    ],
    figures=[
        ("f02_map", "三勢力九城地圖鄰接關係與初始兵力配置", "2.1"),
    ],
    length=(3500, 6000),
    position="基礎世界觀與數學公式：定義三勢力、9 城、42 位武將之數值架構、收入公式與攻城結算。",
    outline="""2.1 版圖與初始狀態：三國三勢力對峙格局，包含 9 城與 42 位武將（每勢力各 14 位），節點鄰接關係與初始資源分佈。
2.2 經濟與維持循環：金錢收入 commerce // GOLD_INCOME_DIV、糧食收入 agriculture // 4，隨機擾動區間 U(0.8, 1.2)；部隊每回合消耗 troops // 10 糧食與斷糧逃兵機制。
2.3 內政開發與武將能力：農業、商業、防禦開發公式與 (50 + politics) 武將政治力乘數。
2.4 軍事調度與攻城門檻：出征最小兵力限制 MIN_SIEGE_TROOPS，戰鬥損耗計算與城防防守結算。
2.5 勝負判定準則：對局結束時依 (城池數, 總兵力) 之字典序裁定勝負。""",
    notes="公式中的整數除法與浮點擾動務必嚴格依原始碼寫出。",
)

chapter(
    n=3, num="3", slug="principles",
    title="設計原則",
    title_en="Design Principles",
    part="第一篇　動機與基礎",
    sources=[ROOT / "docs/DESIGN.md", ROOT / "README.md"],
    must_include=[
        "引擎是唯一的真理來源",
        "Agent 是可替換插件／AI 是可替換的插件／AI 是可替換的「決策插件」",
        "玩家與電腦條件完全對稱",
        "單一種子",
        "可重現",
    ],
    facts=[
        "引擎是唯一的真理來源", "可重現", "單一種子", "玩家與電腦條件完全對稱",
    ],
    figures=[],
    length=(3500, 6000),
    position="架構哲學：軟體工程原則如何指導 AI 遊戲引擎之不可變狀態與對稱性設計。",
    outline="""3.1 引擎是唯一的真理來源：不可變狀態架構（frozen dataclass / copy-on-write），AI 永遠無法直接篡改世界狀態。
3.2 Agent 是可替換的決策插件：統一的代理介面，同套系統無縫切換 LLM、規則 AI、隨機 AI 或人類輸入。
3.3 條件完全對稱性：玩家與電腦適用完全相同的規則、同一套視野限制與注意力預算。
3.4 確定性與可重現性：單一種子偽隨機生成器（PRNG），保證任意對局在相同輸入下 100% 逐位元重現。
3.5 面向審查的工程實踐：拒絕黑盒，讓每一條決策與結算皆具備自解釋日誌。""",
    notes="強調工程原則對科學實驗有效性的支撐作用。",
)

# ==============================================================================
# 第二篇　設計與實作
# ==============================================================================

chapter(
    n=4, num="4", slug="attention",
    title="勢力敘事與注意力經濟",
    title_en="Faction Narration and Attention Economy",
    part="第二篇　設計與實作",
    sources=[
        ROOT / "docs/DESIGN.md",
        ROOT / "src/slg/schema.py",
        ROOT / "src/slg/engine/view.py",
    ],
    must_include=[
        "FactionPlan",
        "orders",
        "chronicle",
        "next_cast",
        "CAST_LIMIT",
        "委任",
        "戰爭迷霧／frontier",
        "forced",
    ],
    facts=[
        "FactionPlan", "orders", "chronicle", "next_cast", "CAST_LIMIT",
        "委任", "forced",
    ],
    figures=[
        ("f04_turn_sequence", "單一回合時序架構：收入、洗牌、決策、委任與結算", "4.1"),
        ("f05_view_blocks", "勢力視野（FactionView）六大組成區塊", "4.3"),
    ],
    length=(3500, 6000),
    position="注意力機制核心：如何透過出場名單聚光燈、戰爭迷霧與強制事件，將 Token 預算化為遊戲機制。",
    outline="""4.1 回合時序架構：收入結算、隨機順序洗牌、視圖生成、計畫制定、指令執行與委任代理。
4.2 勢力計畫 FactionPlan：結構化三元組包含 orders（戰術指令）、chronicle（史書敘事）與 next_cast（下回合聚光名單）。
4.3 出場名單聚光燈 CAST_LIMIT：上限 6 人限制，其餘人員轉為輕量名冊與自動委任。
4.4 戰爭迷霧與邊境 frontier：僅展示相鄰敵城情報，限制情報輸入量並符合古代戰略常理。
4.5 引擎強制介入 forced：突發事件強制登入聚光燈，解決 LLM 注意力盲區。""",
    notes="闡明聚光燈與委任代理的互補關係。",
)

chapter(
    n=5, num="5", slug="engine",
    title="引擎實作與安全網",
    title_en="Engine Implementation and Safety Nets",
    part="第二篇　設計與實作",
    sources=[
        ROOT / "src/slg/engine/legal_actions.py",
        ROOT / "src/slg/engine/validation.py",
        ROOT / "src/slg/engine/game.py",
        ROOT / "src/slg/sim/replay.py",
        ROOT / "src/slg/sim/headless.py",
        ROOT / "README.md",
    ],
    must_include=[
        "generate_legal_actions",
        "validate_decision",
        "resolve_decision",
        "valid == decisions／valid==decisions／stats[\"valid\"] == stats[\"decisions\"]",
        "重播／replay",
        "ReplayDelegateAgent",
        "TurnLog",
    ],
    facts=[
        "generate_legal_actions", "validate_decision", "resolve_decision",
        "ReplayDelegateAgent", "TurnLog",
    ],
    figures=[
        ("f06_safety_net", "引擎驗證安全網流程：合法行動、重試、規則兜底與 rest 保底", "5.2"),
    ],
    length=(3500, 6000),
    position="核心引擎安全防護：從合法動作生成、兩段式驗證到確定性重播系統。",
    outline="""5.1 合法行動枚舉：generate_legal_actions 產生精確動作空間，杜絕非法參數組合。
5.2 嚴格二重驗證：validate_decision 確保狀態未於並行中失效；resolve_decision 安全結算。
5.3 兜底安全網：LLM 輸出無效指令時退回規則 AI，規則失敗則保底執行 rest，確保 valid == decisions。
5.4 完整對局日誌 TurnLog：記錄每回合所有動作、決策來源與結算事件。
5.5 確定性重播：ReplayDelegateAgent 依日誌 100% 重構歷史狀態，杜絕模擬發散。""",
    notes="強調 valid == decisions 是保證遊戲永不崩潰的關鍵不變量。",
)

chapter(
    n=6, num="6", slug="llm_agent",
    title="LLM 代理",
    title_en="LLM Agents and Completer Backends",
    part="第二篇　設計與實作",
    sources=[
        ROOT / "src/slg/agents/llm_agent.py",
        ROOT / "src/slg/agents/backends.py",
        ROOT / "docs/EVALUATION.md",
    ],
    must_include=[
        "SYSTEM_PROMPT",
        "parse_plan",
        "raw_decode／第一個 JSON",
        "CircuitBreakerCompleter",
        "ConfigError",
        "OpenAIChatCompleter",
        "enable_thinking",
        "DemoCompleter",
    ],
    facts=[
        "SYSTEM_PROMPT", "parse_plan", "CircuitBreakerCompleter",
        "ConfigError", "OpenAIChatCompleter", "enable_thinking", "DemoCompleter",
    ],
    figures=[],
    length=(3500, 6000),
    position="代理層實作：結構化提示詞工程、多後端抽象與熔斷器保護機制。",
    outline="""6.1 系統提示詞工程：SYSTEM_PROMPT 規範嚴格輸出契約與短碼格式。
6.2 容錯 JSON 解析：parse_plan 與 raw_decode 從夾帶雜訊之生成文本中精確提取第一個合法 JSON 物件。
6.3 多後端 Completer 架構：OpenAIChatCompleter、離線 DemoCompleter 與外部命令後端。
6.4 思考標記與延遲抑制：關閉 enable_thinking 縮短推論時間，杜絕長鏈推理超時。
6.5 異常隔離與斷路器：CircuitBreakerCompleter 防範連續 API 故障，ConfigError 快速暴露設定缺陷。""",
    notes="深入解析 raw_decode 的魯棒性設計以及斷路器對雲端資源的保護。",
)

chapter(
    n=7, num="7", slug="loyalty",
    title="忠誠、冷落、抗旨與出奔",
    title_en="Loyalty, Neglect, Disobedience, and Defection",
    part="第二篇　設計與實作",
    sources=[
        ROOT / "src/slg/schema.py",
        ROOT / "src/slg/engine/game.py",
        ROOT / "docs/EVALUATION.md",
        ROOT / "docs/DESIGN.md",
    ],
    must_include=[
        "NEGLECT_PENALTY_START",
        "毛遂自薦",
        "DEFECT_BELOW",
        "DISOBEY_BELOW",
        "481／1296",
        "RandomFive",
        "Rotator",
        "Stubborn",
        "Core8",
    ],
    facts=[
        "NEGLECT_PENALTY_START", "毛遂自薦", "DEFECT_BELOW", "DISOBEY_BELOW",
        "481／1296", "RandomFive", "Rotator", "Stubborn", "Core8",
    ],
    figures=[
        ("f07_loyalty_states", "武將忠誠與冷落狀態轉移圖：關注、累積、自薦、抗旨與出奔", "7.1"),
        ("f08_attention_policies", "六種注意力策略下之武將出奔種子比例與最終平均忠誠", "7.3"),
    ],
    length=(3500, 6000),
    position="動態心理機制：君主冷落如何轉化為忠誠衰減，以及 1296 組合網格搜尋之參數調校實踐。",
    outline="""7.1 忠誠動力學模型：關注則獲忠誠提升，連續冷落達到 NEGLECT_PENALTY_START 觸發忠誠損耗。
7.2 危機事件觸發：毛遂自薦機制的介入時機，忠誠低於 DISOBEY_BELOW 之抗旨與低於 DEFECT_BELOW 之出奔。
7.3 注意力策略掃描：五種極端策略（Stubborn、FixedSix、Core8、RandomFive、Rotator）與基準線。
7.4 1296 組合網格調校：481/1296 滿足條件，選定最小變動常數賦予機制實質「牙齒」。
7.5 邊界效應與防禦：無鄰接敵城時的無法出奔缺陷與處置方式。""",
    notes="詳細展示調參前後的忠誠曲線與抗旨出奔數據。",
)

# ==============================================================================
# 第三篇　實驗與結果
# ==============================================================================

chapter(
    n=8, num="8", slug="eval_method",
    title="評測方法",
    title_en="Evaluation Methodology and Harness",
    part="第三篇　實驗與結果",
    sources=[
        ROOT / "docs/EVALUATION.md",
        ROOT / "src/slg/sim/evaluate.py",
        ROOT / "src/slg/sim/batch_eval.py",
    ],
    must_include=[
        "同座位",
        "同種子",
        "max_calls／預算",
        "diagnostics／診斷",
        "advantage",
    ],
    facts=[
        "同座位", "同種子", "diagnostics", "advantage",
    ],
    figures=[
        ("f09_balance", "規則 AI 基準線下 40 種子 30 回合之勝者分布平衡性", "8.2"),
    ],
    length=(3500, 6000),
    position="科學評測架構：對抗式基準線建立、同座位種子控制變因與多維度診斷體系。",
    outline="""8.1 評測哲學：同座位、同種子成對比對，嚴格消除初始地圖不對稱帶來的勝率偏差。
8.2 規則 AI 基準線標定：40 種子 30 回合各勢力 12 勝 4 平局的對稱基準。
8.3 情境設計：default 標準情境 vs advantage 進攻優勢情境之差異與設計目標。
8.4 預算與保護機制：max_calls 呼叫上限防範無窮迴圈與 Token 浪費。
8.5 多維度診斷指標：勝率差、兵力差、接受率、攻城勝率與事件損耗曲線。""",
    notes="強調評測設計中控制變因的核心價值。",
)

chapter(
    n=9, num="9", slug="gemini",
    title="實驗一：Gemini 的三個階段",
    title_en="Experiment I: Three Stages of Gemini-3.5-Flash-Lite",
    part="第三篇　實驗與結果",
    sources=[
        ROOT / "docs/EVALUATION.md",
        ROOT / "docs/evals/*.md",
    ],
    must_include=[
        "84.1%",
        "94.3%",
        "35 次攻城",
        "0 次成功",
        "+472",
        "gemini-3.5-flash-lite",
    ],
    facts=[
        "84.1%", "94.3%", "35 次攻城", "0 次成功", "+472", "gemini-3.5-flash-lite",
    ],
    figures=[
        ("f10_gemini_stages", "Gemini-3.5-flash-lite 三階段實驗之指令接受率與兵力差比較", "9.1"),
        ("f11_rejections", "參數修正前後指令被拒絕原因前三名之分布變化", "9.2"),
    ],
    length=(3500, 6000),
    position="實證分析一：雲端商用輕量模型在漸進工程改善下的三階段實戰反饋。",
    outline="""9.1 階段一：語法與參數障礙。初始接受率僅 84.1%，被拒主因在於目標欄位缺失與型別不符。
9.2 階段二：參數容錯修正。接受率大幅提升至 94.3%，但盲目攻城（35 次攻城，0 次成功）導致兵力嚴重折損。
9.3 階段三：勝算偵察視野引入。LLM 獲得敵方兵力與城防勝算提示後放棄無謀進攻，兵力差反超基準線達 +472。
9.4 指令被拒原因分佈演化：從格式型錯誤轉移為動態規則限制。
9.5 雲端商用模型的特性總結：指令遵循度高，但缺乏戰略全域視野時極易冒進。""",
    notes="聚焦 84.1% -> 94.3% -> +472 的工程迭代轉折。",
)

chapter(
    n=10, num="10", slug="qwen",
    title="實驗二：本機 Qwen 大規模實驗",
    title_en="Experiment II: Large-Scale Local Qwen Experiments",
    part="第三篇　實驗與結果",
    sources=[
        ROOT / "docs/EVALUATION.md",
        ROOT / "docs/evals/qwen/*.md",
    ],
    must_include=[
        "Qwen3.8-27B",
        "+2698",
        "10 / 7／10 次攻城成功 7 次",
        "7 / 0",
        "faction_3",
        "0 次出奔",
    ],
    facts=[
        "Qwen3.8-27B", "+2698", "10 / 7", "7 / 0", "faction_3", "0 次出奔",
    ],
    figures=[
        ("f12_qwen_q1", "本機 Qwen3.8-27B（Q1）三座位之兵力差與指令接受率", "10.1"),
        ("f13_siege_outcomes", "攻城戰績對比：優勢情境與各實驗組之攻城嘗試與攻克次數", "10.2"),
        ("f14_long_games", "Q3 四十回合長局各座位之兵力差分布（全座位出奔次數皆為 0）", "10.3"),
    ],
    length=(3500, 6000),
    position="實證分析二：本機 27B 開源權重大規模評測（Q1–Q4），展現精準出征與長局穩定性。",
    outline="""10.1 Q1 三座位基準測試：孫權席位（faction_3）展現壓倒性兵力積累優勢（兵力差高達 +2698）。
10.2 Q2 進攻優勢情境：在勝算提示下，Qwen 展現極高戰術素養，10 次攻城成功 7 次（10 / 7），遠勝規則 AI 的 7 次 0 成功（7 / 0）。
10.3 Q3 四十回合耐力賽：各座位長局兵力大幅領先，且全程保持 0 次出奔，證實注意力維持之穩定度。
10.4 Q4 自我對弈與座位優勢揭露：faction_3 在封閉地圖邊角的天然地緣優勢。
10.5 開源模型與商用模型之綜合實力對比：本機部署之可行性與戰略潛力。""",
    notes="詳細列出 Q1-Q4 的量化數據，特別是 10/7 vs 7/0 的攻城對比。",
)

# ==============================================================================
# 第四篇　方法論與展望
# ==============================================================================

chapter(
    n=11, num="11", slug="method_dev",
    title="開發方法論：分層外包與驗收",
    title_en="Development Methodology: Layered Outsourcing and Verification",
    part="第四篇　方法論與展望",
    sources=[ROOT / "HANDOFF.md", ROOT / "docs/EVALUATION.md", ROOT / "README.md"],
    must_include=[
        "agy",
        "Qwen",
        "nim／worker",
        "突變測試",
        "不採信 worker 自述",
        "斷路器",
    ],
    facts=[
        "agy", "Qwen", "突變測試", "不採信 worker 自述", "斷路器",
    ],
    figures=[
        ("f15_orchestration", "主管 AI 與外包 Worker（agy、Qwen、nim）之分工協作與驗收迴圈", "11.1"),
    ],
    length=(2500, 5000),
    position="方法論核心：現代 AI 輔助軟體工程實踐，主管 AI、雲端 worker 與本機 worker 之分工與對抗驗收。",
    outline="""11.1 分層外包架構：主管 AI（規格制定與審查）＋雲端 agy（複雜程式碼撰寫）＋本機 Qwen（無額外成本實驗與調參）＋nim-staff 跨域協同。
11.2 不採信 worker 自述原則：杜絕「虛假完成」，完全依賴可重現測試與數據結晶。
11.3 嚴格驗收流水線：單元測試全過、種子回歸一致性檢驗與突變測試（mutation testing）防範無效斷言。
11.4 基礎設施防護網：保護雲端配額的斷路器機制與長任務暫停點管理。
11.5 軟體工程實踐啟示：AI 輔助開發的關鍵在於邊界定義與獨立驗證預言機。""",
    notes="強調不採信自述與突變測試的對抗性驗證哲學。",
)

chapter(
    n=12, num="12", slug="limits",
    title="已知缺陷與開放問題",
    title_en="Known Limitations and Open Problems",
    part="第四篇　方法論與展望",
    sources=[ROOT / "HANDOFF.md", ROOT / "docs/EVALUATION.md"],
    must_include=[
        "rest",
        "座位",
        "宛城",
        "漢中",
        "中途不可見",
    ],
    facts=[
        "rest", "座位", "宛城", "漢中", "中途不可見",
    ],
    figures=[],
    length=(3500, 6000),
    position="批判性檢視：客觀記錄現行系統的設計限制、地緣邊界問題與評測盲點。",
    outline="""12.1 決策惰性與消極休整：rest 行動比例高達 ~47%，反映出深層戰略誘因設計之不足。
12.2 地緣結構與座位優勢：東南孫權（faction_3）邊角優勢導致自我對弈失衡，曹操多線受敵。
12.3 叛逃封閉性缺陷：宛城與漢中武將因深處後方且不與敵城相鄰，在規則定義下完全無法出奔。
12.4 評測流水線黑盒性：evaluate 工具整組實驗結束後才落地寫檔，長局中途不可見。
12.5 資源爭用與決策反饋之粗糙性：同城多武將金幣爭用被拒達 20%，攻城歸因提示仍顯單薄。""",
    notes="誠實面對系統短板，不粉飾缺陷。",
)

chapter(
    n=13, num="13", slug="roadmap",
    title="下一步與實驗路線圖",
    title_en="Next Steps and Experimental Roadmap",
    part="第四篇　方法論與展望",
    sources=[
        ROOT / "HANDOFF.md",
        ROOT / "docs/EVALUATION.md",
        ROOT / "docs/DESIGN.md",
    ],
    must_include=[
        "玩家介面",
        "信賴區間",
        "各城可用金幣預算",
        "gemini-3.5-flash",
    ],
    facts=[
        "玩家介面", "信賴區間", "各城可用金幣預算", "gemini-3.5-flash",
    ],
    figures=[
        ("f16_roadmap", "研究與開發路線圖：已完成里程碑與後續規劃", "13.1"),
    ],
    length=(2500, 5000),
    position="全書展望：從工程原型邁向完整遊戲與嚴謹學術基準的演進路徑。",
    outline="""13.1 近期工程改善：視圖引入各城可用金幣預算，消除資源競爭引起的指令被拒。
13.2 評測體系升級：擴大種子規模、導入信賴區間統計檢定，平衡初始地緣以重啟自我對弈。
13.3 玩家互動與人機介面：將人類玩家封裝為 FactionAgent，驗證分層注意力機制的人類體驗。
13.4 模型能力階梯測試：引入 gemini-3.5-flash 等高階推理模型，探索戰略規劃能力的邊界。
13.5 未來展望：自主敘事策略遊戲的完整生態構想。""",
    notes="描繪清晰的三階段演進藍圖。",
)

chapter(
    n=14, num="A", slug="appendix",
    title="附錄：術語表、指令速查、檔案地圖",
    title_en="Appendix: Glossary, Command Reference, and File Map",
    part="第四篇　方法論與展望",
    sources=[ROOT / "README.md", ROOT / "HANDOFF.md"],
    must_include=[
        "PYTHONPATH=src",
        "python3 -m unittest",
        "evaluate",
        "run_llm",
    ],
    facts=[
        "PYTHONPATH=src", "python3 -m unittest", "evaluate", "run_llm",
    ],
    figures=[],
    length=(3000, 5000),
    position="附錄與速查工具：提供專案術語對照、核心指令與模組架構導覽。",
    outline="""A.1 術語對照表：君主、太守、武將、注意力聚光燈、確定性重播等關鍵詞中英對照。
A.2 核心指令速查：PYTHONPATH=src 環境變數配置、python3 -m unittest 測試指令、evaluate 評測工具與 run_llm 實時對局。
A.3 專案檔案地圖：src/slg/ 引擎核心、sim/ 模擬工具、agents/ 代理層與 docs/ 文件組織。
A.4 重現性實驗指引：如何一鍵重跑 40 種子基準線與離線 Demo。""",
    notes="保持速查表的實用性與精確性。",
)

# ==============================================================================
# 圖表英文圖說對照表 (FIG_EN)
# ==============================================================================

FIG_EN = {
    "f01_architecture": "Hierarchical AI decision architecture and dataflow: from game state to deterministic replay",
    "f02_map": "Adjacency graph of nine cities across three factions with initial troop distribution",
    "f03_token_cost": "Estimated token consumption per turn across four decision architectures",
    "f04_turn_sequence": "Single-turn execution sequence: income, shuffle, plan, delegation, and resolution",
    "f05_view_blocks": "The six structural blocks of FactionView under fog of war and cast spotlight",
    "f06_safety_net": "Engine validation safety net: legal actions, retries, fallback agent, and rest",
    "f07_loyalty_states": "Officer loyalty and neglect state transition diagram",
    "f08_attention_policies": "Defection seed ratio and final average loyalty across six attention policies",
    "f09_balance": "Winner distribution balance across 40 seeds (30 turns) under rule-based baseline",
    "f10_gemini_stages": "Acceptance rate and troop delta across three Gemini-3.5-flash-lite stages",
    "f11_rejections": "Top-3 rejection reasons before and after parameter normalization",
    "f12_qwen_q1": "Troop delta and order acceptance rate across three seats in Qwen3.8-27B (Q1)",
    "f13_siege_outcomes": "Siege outcomes: attempts vs captures in advantage scenario and experimental runs",
    "f14_long_games": "Troop delta across seats in 40-turn games (zero defections across all seats)",
    "f15_orchestration": "Orchestration and verification loop: supervisor AI with agy, Qwen, and nim",
    "f16_roadmap": "Research and development roadmap: completed milestones and planned horizons",
}

FIG_CAPTIONS = {fid: cap for c in CHAPTERS for fid, cap, _ in c["figures"]}
