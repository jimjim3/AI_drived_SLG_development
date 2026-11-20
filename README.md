# AI-Driven SLG(AI 分層決策的三國式策略遊戲)

免費、開源、網頁版的三國策略遊戲實驗:君主、太守、武將的決策都可以由 AI(LLM)扮演,而「每一層能做什麼」完全由遊戲引擎決定並驗證。玩家與 AI 看到同樣的畫面、遵守同樣的規則。

> English summary: an open-source, browser-based Three Kingdoms strategy game where LLM agents play the rulers. A deterministic Python engine owns the rules and validates every action (agents only choose among legal actions); players and AIs share the same fog-of-war view and interface. Standard library only, no build step. Runs offline with rule-based AIs; LLM opponents plug in through any OpenAI-compatible endpoint.

## 現況(2026-11)
- **可玩**:9 城、3 勢力(曹操、劉備、孫權)、42 武將,戰爭迷霧,網頁介面(地圖、城池、武將、軍令、外交同盟、戰報敘事),存檔與續玩。
- **AI**:規則 AI(離線)、LLM 勢力代理(Nemotron、Qwen、Gemini 等,OpenAI 相容端點)、錯誤重試與退回規則 AI 的安全網。
- **機制**:距離折損、經濟與城池規模規則、忠誠與冷落、同盟(友好度、抵押、背盟),全部由規則集旗標控制,預設 `v2` 不變。
- **品質**:474 個單元測試;瀏覽器端到端腳本 `scripts/e2e_web.py`、`scripts/e2e_alliance.py`;確定性重播。
- **尚未做**:太守與武將層的 LLM 決策、部隊行軍與野戰、多劇本、真人試玩資料。**沒有真人試玩過。**
- **路線圖**:[docs/ROADMAP.md](docs/ROADMAP.md)(目標、系統藍圖、里程碑 M0–M4)。接手請先讀 [HANDOFF.md](HANDOFF.md)。

## 快速開始
需要 Python 3.10 以上,只用標準函式庫。

```sh
python3 -m unittest                              # 跑測試(專案根目錄)
scripts/serve.sh                                 # 網頁介面 http://127.0.0.1:8080/
PYTHONPATH=src python3 -m slg.sim.run_llm --demo --turns 3   # 離線示範對局
```

要玩 LLM 對手、遠端試玩、存檔位置等,見 [deploy/README.md](deploy/README.md)。金鑰只放環境變數,不進 repo。

## 文件地圖
| 文件 | 內容 |
|---|---|
| [docs/ROADMAP.md](docs/ROADMAP.md) | 完整路線圖與已決定事項 |
| [docs/DESIGN.md](docs/DESIGN.md) | 架構設計:分層、行動空間、Token 預算、抗旨機制 |
| [docs/DESIGN_ALLIANCE.md](docs/DESIGN_ALLIANCE.md) | 同盟機制設計 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 評測方法與全部實驗紀錄(§1–§22) |
| [docs/PRIOR_ART.md](docs/PRIOR_ART.md) | 參考專案與版權注意事項 |
| [data/sanguo/README.md](data/sanguo/README.md) | 三國資料庫(105 城、29 個時期劇本草稿;**未核實,引擎尚未使用**) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 如何參與、資料與版權規則 |

## 設計原則
1. **引擎是唯一的真理來源**:AI 只能從 `generate_legal_actions` 的清單中挑選,`validate_decision` 執行前再重驗,AI 不直接改狀態。
2. **玩家與 AI 對稱**:同一個視野、同一個介面、同一套規則。
3. **AI 是可替換的插件**:規則、隨機、LLM、人類共用 `Agent` / `FactionAgent` 介面。
4. **可重現**:單一種子亂數與完整決策日誌,`replay` 可 100% 還原。
5. **能離線玩**:沒有 LLM 時規則 AI 也能完整跑完一局。

## 程式結構
```
src/slg/
  schema.py            資料結構(GameState、CityState、OfficerState、FactionPlan、FactionView…)
  engine/              initial_state、legal_actions、validation、resolution、game、view、combat(規則集)、alliance
  agents/              rule_based、random_agent、llm_agent、backends(OpenAI 相容、CLI、離線示範)
  sim/                 headless、replay、run_llm、evaluate、batch_eval
  narrative/           劇情文本(武將傳略、事件模板、開場)
  web/                 server、session、payload、savegame、static(前端)
scripts/               selfplay(評測)、e2e_*(瀏覽器測試)、資料生成與驗證、教科書工具
data/sanguo/           資料庫(尚未接入引擎)
docs/                  設計、評測、路線圖、美術、教科書草稿
tests/                 單元測試
```

## 授權
程式碼採 MIT(見 [LICENSE](LICENSE))。資料與美術的授權狀態見 [NOTICE.md](NOTICE.md);**在該文件寫明之前,不要把 `data/` 內的模型生成資料或 Koei 參考值當成可再散布的資料。**

---

# 附錄:早期階段紀錄(2026-10,部分數字已過時)

## 早期實作紀錄

- **劇本與地圖**：
  - 5 城（許昌、陳留、襄陽、洛陽、建業）、3 勢力（曹操、劉備、孫權）、20 武將初始配置。
  - 鄰接地圖拓撲：陳留–許昌–洛陽、許昌–襄陽、襄陽–洛陽、襄陽–建業。
- **遊戲引擎與規則 v2（`src/slg/engine/`）**：
  - `initial_state.py`：5 城 3 勢力 20 武將初始狀態；洛陽、建業享有高初始資源與兵力的首都加成。
  - `legal_actions.py`：依城池與武將狀態動態產生合法行動清單；開發增量隨武將政治力動態成長；攻城可選出征兵力（`min=500`、留守 `min=100`、級距 100）。
  - `validation.py`：執行前對 AI 決策進行嚴格二次重驗（行動名、參數範圍、金錢成本、前置條件）。
  - `resolution.py`：全由種子亂數驅動之純函數結算（開發、徵兵、移動、休息、攻城攻防、俘虜轉投）。
    - 戰鬥公式結合出征部隊、武將武力與統御（`war + leadership`）、守方駐軍、城防值與城內最優守將能力。
    - 滅國轉投：最後城池陷落時，存活武將轉投攻方勢力（忠誠上限 60）。
  - `game.py`：回合主迴圈（收入維持 → 勢力決策 → 委任代理 → 狀態更新）。
    - 收入與維持：金錢 `commerce // 3`、糧食 `agriculture // 4`（各帶 U(0.8, 1.2) 隨機擾動）；每回合部隊消耗 `troops // 10` 糧食，糧荒時糧食歸零且部隊發生 10% 逃兵（`troops * 9 // 10`）。
    - 行動順序：每回合各勢力行動順序以種子隨機洗牌。
    - 勝負判定：依 `(城池數, 總兵力)` 字典序評定勝負。
    - 安全網機制：AI 決策異常/非法時自動重試，重試耗盡退回規則 AI，兜底 `rest`，確保 `valid == decisions`。
- **勢力層級決策與視野迷霧（`src/slg/engine/view.py`）**：
  - `FactionAgent.decide(FactionView) -> FactionPlan(orders, chronicle, next_cast)` 統一介面。
  - 戰爭迷霧：勢力視野僅能見到己方城池與相鄰敵方前線城池（`frontier`），其餘後方敵城不可見。
  - 出場名單聚光燈（`select_cast`）：上限 `CAST_LIMIT = 6`，優先順序為 forced（受攻/被俘） → requested（LLM 點名） → 各城綜合最強武將 → 其餘武將排序。
  - 委任代理（Delegation）：未被 LLM 點名之存活武將，由 `Game` 自動交由委任代理（預設 `RuleBasedAgent("balanced")`）補足行動。
  - 拒絕指令反饋：被引擎拒絕的指令與原因，自動彙整為反饋清單傳遞至下回合視野。保留官員層級 `Agent` 相容支援。
- **AI 插件層與 Completer 後端（`src/slg/agents/`）**：
  - `RuleBasedAgent`：三種風格（`balanced`、`aggressive`、`turtle`），依兵力對比動態權衡攻城與內政。
  - `RandomAgent`：在合法參數格點上隨機抽樣。
  - `LLMFactionAgent`（別名 `LLMAgent`）：結構化 JSON 解析、帶錯誤反饋自動重試（`max_retries`）、字元/Token 計數（`usage`）。
  - Completer 後端（`backends.py`）：
    - `DemoCompleter`：離線規則示範，無需網路即可體驗完整勢力決策流程。
    - `OpenAIChatCompleter`：基於 Python 標準庫 `urllib` 調用 OpenAI 相容 `/chat/completions` API。
    - `CommandCompleter`：透過子程序調用 CLI 工具（支援 stdin 與 `{prompt_file}`）。
    - `ScriptedCompleter`：單元測試專用。
- **Headless 模擬、CLI 與重播（`src/slg/sim/`）**：
  - `headless.py`：`run_headless(seed, turns, agents_by_faction)`，支援勢力/官員 AI、記錄 `TurnLog`、回傳 `GameResult`（含 usage 統計）。
  - `run_llm.py`：CLI 入口，支援 `--demo`、OpenAI 端點、指定 LLM 勢力、儲存日誌等。
  - `replay.py`：記錄每勢力每回合實際執行的決策（`FactionTurnLog.executed`），以 `replay(log)` 完全還原相同的狀態遷移與解析事件。
- **測試（`tests/`）**：
  - 146 個 unittest 測試全數通過，涵蓋各規則結算、地圖鄰接、出征兵力邊界、戰鬥攻防、滅國轉投、Completer 後端、重播一致性、數值平衡迴歸（30 回合 40 種子統計驗證）等。

### 實測驗證（Gemini 3.5 Flash Lite）

2026-10-10 以真實 Gemini（`gemini-3.5-flash-lite`，OpenAI 相容端點 `https://generativelanguage.googleapis.com/v1beta/openai`）實測 3 回合（`faction_2` 為 LLM）：
- 3 次呼叫、約 5k tokens（粗估）
- 16 個指令 0 拒絕、0 解析失敗

### 早期程式結構

```
AI_drived_SLG_development/
├── pyproject.toml            # setuptools src-layout 專案定義
├── LICENSE                   # MIT
├── docs/
│   ├── DESIGN.md             # 架構設計、里程碑與實作對照
│   └── PRIOR_ART.md          # 參考專案與版權注意事項
├── src/slg/
│   ├── schema.py             # 資料結構（CityState/OfficerState/FactionState/GameState/FactionPlan/FactionView 等）與常數
│   ├── engine/
│   │   ├── initial_state.py  # build_initial_state()：5 城 3 勢力 20 武將初始狀態與鄰接地圖
│   │   ├── legal_actions.py  # generate_legal_actions()：政治力加成、可選兵力攻城
│   │   ├── validation.py     # validate_decision()：執行前嚴格二次重驗
│   │   ├── resolution.py     # resolve_decision()：結算效果、攻守戰鬥公式、滅國投降
│   │   ├── game.py           # Game：回合主迴圈、收入 upkeep、勢力決策處理、委任代理與安全網
│   │   └── view.py           # FactionView、select_cast、forced_cast、戰爭迷霧與事件描述
│   ├── agents/
│   │   ├── base.py           # Agent（官員層級）、FactionAgent（勢力層級）抽象介面
│   │   ├── rule_based.py     # RuleBasedAgent（balanced / aggressive / turtle 風格）
│   │   ├── random_agent.py   # RandomAgent（合法參數隨機抽樣）
│   │   ├── backends.py       # Completer 後端（OpenAIChatCompleter, CommandCompleter, DemoCompleter, ScriptedCompleter）
│   │   └── llm_agent.py      # LLMFactionAgent（結構化 JSON 解析、帶錯重試、字元/Token 計數）
│   └── sim/
│       ├── headless.py       # run_headless() / GameResult（支援官員與勢力 AI、usage 統計）
│       ├── replay.py         # replay() / ReplayFactionAgent：依 TurnLog 確定性完全重播
│       └── run_llm.py        # CLI 入口：支援 --demo 與 OpenAI API 相容後端
└── tests/
    ├── test_agents.py        # 官員層級 Agent 合法性
    ├── test_backends.py      # 各 Completer 後端行為與異常處理
    ├── test_balance.py       # 30 回合數值平衡與勝率分佈迴歸
    ├── test_full_game.py     # 完整對局與勝負判定
    ├── test_game_faction.py  # 勢力層級 Game 流程、委任代理、迷霧與反饋
    ├── test_llm_faction.py   # LLMFactionAgent 解析、重試與容錯
    ├── test_replay_faction.py# 確定性重播一致性驗證
    ├── test_reproducibility.py# 同種子完整重現
    ├── test_resolution.py    # 行動結算效果
    ├── test_rules_v2.py      # 規則 v2（地圖鄰接、糧草維持、出征兵力、戰鬥公式、滅國）
    ├── test_run_llm.py       # run_llm CLI 與 DemoCompleter 端到端
    ├── test_safety_net.py    # 異常 Agent 安全網兜底
    ├── test_validation.py    # 行動驗證器各項邊界條件
    └── test_view.py          # 勢力視野、出場名單挑選、迷霧與事件過濾
```

### 早期執行方式

環境：Python 3.10+，僅用標準函式庫（`unittest`、`random`、`dataclasses`、`urllib`），無需安裝任何第三方套件。

```sh
# 1. 跑測試（專案根目錄）
python3 -m unittest

# 2. 離線示範對局（使用 DemoCompleter，無需 API key）
PYTHONPATH=src python3 -m slg.sim.run_llm --demo --turns 3

# 3. 真實 LLM 對局（以 Gemini 3.5 Flash Lite 透過 OpenAI 相容端點為例）
GEMINI_API_KEY=$GEMINI_API_KEY PYTHONPATH=src python3 -m slg.sim.run_llm \
  --seed 3 \
  --turns 3 \
  --llm-faction faction_2 \
  --openai-base-url https://generativelanguage.googleapis.com/v1beta/openai \
  --model gemini-3.5-flash-lite \
  --api-key-env GEMINI_API_KEY

# 4. Headless 規則 AI 對局
PYTHONPATH=src python3 -c "
from slg.sim.headless import run_headless
r = run_headless(seed=42, turns=20)
print('winner:', r.winner)
print('stats:', r.stats)
"
```

### 早期設計原則

1. **引擎是唯一的真理來源**：AI 只能從 `generate_legal_actions` 的清單中挑選，`validate_decision` 在執行前再嚴格重驗；AI 永遠不直接修改遊戲狀態。
2. **勢力敘事與分層委任**：每勢力每回合僅呼叫一次 LLM 產出戰略重點指令（`orders`）與紀事（`chronicle`）；沒被點名的武將由規則 AI 委任代理；配合戰爭迷霧與出場名單上限（`CAST_LIMIT = 6`），防止輸入 Token 隨勢力規模爆炸。
3. **AI 是可替換的插件**：統一 `Agent` 與 `FactionAgent` 介面；支援多種 Completer 後端（OpenAI API、本機 CLI、離線示範）；LLM 解析失敗或異常時自動帶錯誤反饋重試，重試耗盡自動退回規則 AI 兜底（`game.py` 安全網）。
4. **可重現與確定性**：單一種子亂數源；`TurnLog` 完整記錄每勢力實際執行之決策，由 `replay` 模組達成 100% 相同之狀態與事件重現。

### 早期下一步(已被路線圖取代)

- **M2 剩餘項目**：冷落機制（武將長期未出場忠誠下降、懷才不遇、自薦出奔事件）。
- **M3**：忠誠/偏離機制（抗旨擲骰判定、偏離選項）、武將人物記憶、重大時刻聚光燈單獨呼叫。
- **M4**：客觀評測體系（LLM vs 同座位規則 AI 基準線之勝率、Token 消耗率、敘事與結算狀態一致性）。
- **M5**：視覺化前端（Web / GUI）。

### 早期限制(多數已解決,見 HANDOFF)

專案當前為階段性實驗原型，已知限制如下，誠實記錄以利後續評測與迭代：

1. **休息（`rest`）比例偏高（約 66%）**：每座城池分配武將較多（如許昌 4 人、洛陽 6 人），但每回合城池金錢收入僅足夠支應約 2～3 個需要金錢的行動（如開發或募兵），金錢耗盡後其餘武將多數只能選擇 `rest`。
2. **初始版圖與勝率結構不對稱**：曹操勢力（`faction_1`）初始擁有 3 城，對上僅有單城的劉備（`faction_2`）與孫權（`faction_3`），在規則 AI 基準線下勝率約 70%（因此評測 LLM 實力時，應與「同座位的規則 AI 基準線」作勝率比較，而非直接與其他勢力比較）。
3. **攻城勝利後武將留在出發城**：攻城勝利結算時，出征獲勝部隊會進駐佔領城市作為守軍，但出征武將本人的所在地目前仍停留在出發城市（僅部隊進駐，武將未跟隨移駐）。
4. **出場名單上限尚未被真正檢驗**：劉備（`faction_2`）與孫權（`faction_3`）麾下武將總數皆為 6 人，恰好等於 `CAST_LIMIT = 6`；出場名單的輪替與篩選機制目前主要僅在擁有 8 位武將的曹操勢力（`faction_1`）受到檢驗。
5. **未實作機制**：
   - 連續未受點名武將的「冷落」機制（忠誠下降、出奔）尚未實作；
   - 抗旨、叛變與忠誠度動態計算尚未實作；
   - 正式史書在結算後書寫尚未實作（目前 `chronicle` 於事前決策當下生成）；
   - 人類玩家介面（UI / Web）尚未實作。
