# AI-Driven SLG（AI 分層決策的三國式策略遊戲）

實驗性開源專案：在類似 KOEI《三國志》的回合制 SLG 中，讓 **君主 → 太守 → 武將** 每一層的行動都由 AI（LLM）決定，
而「每一層允許做什麼」完全由遊戲引擎決定與驗證。

- [docs/DESIGN.md](docs/DESIGN.md) — 架構設計（分層、行動空間、Token 預算、抗旨機制、評測）
- [docs/PRIOR_ART.md](docs/PRIOR_ART.md) — 可參考 / 可改造的開源專案與版權、專利注意事項

## 狀態

**M0a 已完成：可執行的遊戲核心骨架。** 引擎能產生、驗證、結算合法行動；AI 以可替換插件介面接入；
規則 AI 可在 headless 模式用固定種子完整跑完 20 回合且可重現。尚無 LLM 接入與前端。

## M0a 做了什麼

- **遊戲引擎（`src/slg/engine/`）**：唯一的真理來源。
  - `initial_state.py`：3 城（許昌、陳留、洛陽）、2 勢力（曹操、劉備）、10 武將的迷你劇本。
  - `legal_actions.py`：依武將與城池狀態動態產生合法行動清單（含參數範圍與成本）。
  - `validation.py`：執行前對 AI 決策再驗證一次（行動名、參數範圍、成本、前置條件）。
  - `resolution.py`：結算行動效果（開發、徵兵、移動、攻城攻防、俘虜與遷移），全部以種子亂數驅動。
  - `game.py`：回合主迴圈（收入 → 決策 → 結算 → 勢力狀態），並提供安全網：
    AI 決策失敗 → 重試一次 → 退回規則 AI → 最終兜底 `rest`，保證 `valid == decisions`。
- **行動空間**：`develop_agri` / `develop_commerce` / `develop_defense` / `recruit` / `move` / `siege` / `rest`。
- **AI 插件層（`src/slg/agents/`）**：統一 `Agent.decide(state, officer, legal)` 介面。
  - `RuleBasedAgent`：攻城 → 徵兵 → 開發 → 休息的優先序，M0a 的預設 AI。
  - `RandomAgent`：在合法參數格點上隨機抽樣，用於對照與安全網測試。
  - 同一介面之後可接 LLM、人類玩家，互不影響。
- **Headless 模擬（`src/slg/sim/headless.py`）**：`run_headless(seed, turns, agents_by_faction)`，
  單一種子亂數源，回傳最終狀態、決策統計（`decisions/valid/rejected/fallbacks`）、事件流水與勝負。
- **測試（`tests/`）**：27 個 unittest 測試，涵蓋行動產生、驗證、結算、可重現性、完整對局、安全網。

### 驗證結果

```
$ python3 -m unittest
Ran 27 tests in 0.029s

OK
```

Headless 對局（seed=42、20 回合、雙方規則 AI）範例輸出：

```
winner: faction_1
stats: {'decisions': 200, 'valid': 200, 'rejected': 0, 'fallbacks': 0}
events: 200
曹操: ['xuchang', 'chenliu']
劉備: ['luoyang']
actions: Counter({'rest': 133, 'recruit': 47, 'develop_agri': 18, 'siege': 2})
```

## 程式結構

```
AI_drived_SLG_development/
├── pyproject.toml            # setuptools src-layout 專案定義
├── LICENSE                   # MIT
├── docs/
│   ├── DESIGN.md             # 架構設計與里程碑
│   └── PRIOR_ART.md          # 參考專案與版權注意事項
├── src/slg/
│   ├── schema.py             # 資料結構（CityState/OfficerState/FactionState/GameState）
│   │                         # 與可調常數（開發成本、徵兵上下限、攻城門檻…）
│   ├── engine/
│   │   ├── initial_state.py  # build_initial_state()：3 城 2 勢力 10 武將
│   │   ├── legal_actions.py  # generate_legal_actions()
│   │   ├── validation.py     # validate_decision()
│   │   ├── resolution.py     # resolve_decision()
│   │   └── game.py           # Game：回合主迴圈 + 安全網
│   ├── agents/
│   │   ├── base.py           # Agent 抽象介面 + AgentDecision
│   │   ├── rule_based.py     # RuleBasedAgent
│   │   └── random_agent.py   # RandomAgent
│   └── sim/
│       └── headless.py       # run_headless() / GameResult
└── tests/
    ├── test_agents.py        # 兩個 Agent 只輸出合法決策
    ├── test_validation.py    # 驗證器接受合法、拒絕非法
    ├── test_resolution.py    # 各行動的結算效果
    ├── test_reproducibility.py # 同種子完整重現
    ├── test_full_game.py     # 20 回合完整對局、勝負判定
    └── test_safety_net.py    # 壞 Agent 被安全網兜底
```

## 執行方式

環境：Python 3.14，僅用標準函式庫（`unittest`、`random`、`dataclasses`），無需安裝任何套件。

```sh
# 跑測試（專案根目錄）
python3 -m unittest

# headless 對局
PYTHONPATH=src python3 -c "
from slg.sim.headless import run_headless
r = run_headless(seed=42, turns=20)
print('winner:', r.winner)
print('stats:', r.stats)
"
```

## 設計原則（實作對應）

1. **引擎是唯一的真理來源**：AI 只能從 `generate_legal_actions` 的清單中挑選，`validate_decision` 執行前再驗一次；AI 永不直接改狀態。
2. **AI 是可替換插件**：`Agent` 介面統一；LLM 掛掉可自動退回規則 AI（`game.py` 安全網）。
3. **可重現**：單一種子亂數源；所有決策與事件可記錄、可重播（M1 會補完整回合日誌）。

## 下一步

- **M0b**：擴充劇本至 5 城、3 勢力、~20 武將；LLM Agent 接入（tool calling / JSON Schema 結構化輸出）；完整回合日誌與重播。
- **M1**：勢力敘事模式（每勢力每回合一次呼叫，`orders` + `chronicle`）。
- **M2**：出場名單 `next_cast`、引擎強制插入事件、冷落機制。
- **M3**：忠誠/偏離機制、人物記憶、聚光燈單獨呼叫。
- **M4**：評測報告（LLM vs 規則 AI）。
- **M5**：前端。
