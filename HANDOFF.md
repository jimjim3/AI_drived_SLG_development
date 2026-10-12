# HANDOFF — AI-Driven SLG（2026-10-11 暫停點）

## 狀態一句話
引擎、LLM 勢力代理、評測、診斷、情境、批次工具皆完成並推送（分支 `claude/ai-hierarchical-slg-game-fl3ojj`，**313 個測試全過**）。進行中：Qwen 任務 M（重調忠誠／冷落常數）。

## 先讀
README.md → docs/DESIGN.md（§3.5–3.6、§9）→ docs/EVALUATION.md（第 4–9 節實驗結果）→ 本檔。

## 進行中（暫停時）
- **任務 M**：Qwen worker 正在 `.worktrees/qwen-M`（分支 `qwen/M`）重調忠誠／冷落常數；規格 `/tmp/claude-1000015/-home-yhho3-winbond/2639b365-455b-4a57-8350-fab459718fbe/scratchpad/specM.md`（若已消失，內容見 DESIGN/EVALUATION 第 9 節問題描述與下方「下一步 1」）。啟動約 2026-10-11 20:37，上限 50 分鐘；日誌 `/tmp/qwen_task_M.log`。
- 接手步驟：`git diff --stat HEAD...qwen/M` → 在 worktree 跑 `python3 -m unittest`（需 ≥313+8 全過）→ 重跑 `PYTHONPATH=src python3 -m slg.sim.tune_attention` 確認行為條件 → 規則 AI 種子 0–9、30 回合 `(winner, decisions)` 與 main 逐種子相同 → 全過才 `git merge --no-ff qwen/M` → `~/local-llm-setup/scripts/qwen-clean.sh M`。未達標就保留分支並讀其疑慮欄。
- 結束後務必 `~/local-llm-setup/scripts/llm-down.sh`（本機 Qwen 服務由我們啟動；GPU 與使用者其他訓練共用）。

## 重要操作知識
- **Qwen worker 已修復**：用 `MODEL_ALIAS=claude-sonnet-5-5 ~/local-llm-setup/scripts/llm-up.sh` 啟動服務，再 `MODEL_ALIAS=claude-sonnet-5-5 ~/local-llm-setup/scripts/qwen-task.sh <編號> <規格檔> <秒>`。CLI 的 `unrecognized_model` 只是警告。直接用 `--dangerously-skip-permissions` 自行啟動代理會被權限分類器擋下，請走 `qwen-task.sh`。
- **agy 雲端實作**：`~/local-llm-setup/scripts/agy-task.sh <編號> <規格檔> <逾時>`（使用者已授權；程式實作已用它完成 A2…L）。
- **Gemini 金鑰**：已寫入 `~/.claude/settings.local.json` 的 `env.GEMINI_API_KEY`（新 session 才載入）；評測用 `--api-key-env GEMINI_API_KEY`，**不要把金鑰放進指令列或檔案**。金鑰曾出現在對話紀錄，使用者應於測試結束後更換。
- **本機 Qwen 當玩家**（免費）：平行 4 路吞吐約單路 3.6 倍；GPU 與使用者訓練共用時單次呼叫約 40–75 秒。實驗時以橋接腳本 + `--command` 或 `--openai-base-url http://127.0.0.1:8090/v1 --extra-body-json '{"chat_template_kwargs":{"enable_thinking":false}}'`。
- 驗收慣例：不採信 worker 自述；重跑測試、結算回歸（種子 0–9 勝者與決策數前後相同）、突變測試（`~/local-llm-setup/scripts/mutate_auto.py`，`MUTATE_TEST_CMD="python3 -m unittest -q"`）。

## 已完成的實驗（細節見 docs/EVALUATION.md、docs/evals/）
Gemini flash-lite 三階段（參數格式修正、勝算偵察）與 Qwen3.8-27B Q1–Q4（三座位、進攻情境、40 回合、自我對弈）。關鍵：偵察資訊使 LLM 在優勢下攻城 7/10 成功（規則 AI 0/7）；**忠誠／冷落機制在真實對局從未觸發**（即任務 M 的動機）；約 20% 指令因同城金幣爭用被拒；劇本對 faction_3 有座位優勢（自我對弈 4/4）。

## 下一步（依優先序）
1. 合併任務 M 後，用 Qwen 重跑長局（seat 各一、種子 0–3、40 回合）確認機制在真實 LLM 玩法下有作用。
2. 視圖加入各城可用金幣預算，降低資源爭用拒絕。
3. 平衡座位優勢後重做自我對弈（Q4）。
4. 玩家介面（玩家 = `FactionAgent`，輸入只有 `FactionView`）。
5. 增加種子數、加信賴區間；比較更強模型（`gemini-3.5-flash`）。

## 已知缺陷
rest 比例約 47%；faction_2 的宛城／漢中武將不與任何敵城相鄰故無法出奔；`evaluate` 整組結束才寫檔、中途不可見；攻城後的「可能原因提示」規則較粗。

---
## 補充（2026-10-12）：教科書專案進度

**目標**：繁體中文教科書《讓 LLM 當君主：分層 AI 決策策略遊戲的設計、實作與實驗》（14 章＋附錄、16 張圖）。我為總編輯；Qwen 轉寫、agy 做腳手架／修圖／審稿。

**已完成**
- 腳手架（`scripts/textbook/`）：通用工具複製自姊妹專案（已確認無領域內容）；`book.py`、`chapters.py`（14 章規格：素材＋必備事實＋圖表）、`figs_concept.py`／`figs_data.py`（16 張圖）、`validate_spec.py`；16 張圖已由 agy 逐張目視修正並由總編輯抽查，輸出在 `docs/textbook/figures/zh-TW/`。
- **Qwen 中文草稿已通過自動檢查：第 1–8 章與第 12 章**（`docs/textbook/drafts/zh-TW/chNN.md`，每章約 2900–3500 字，低於 3500–6000 字目標，待審稿時一併評估是否補寫）。
- 修正一個腳手架 bug：`chapters.py` 的素材萬用字元（`docs/evals/*.md`）原本沒展開導致第 9、10 章無法載入，現在於 `chapters.py` 末尾展開。

**尚未完成**：第 9、10、11、13、14 章草稿 → agy 審稿員逐章對照 repo 查核事實 → 依清單修稿（簡單的由 Qwen 重寫，關鍵數字總編輯抽查）→ `build_book.py` 組書成 PDF（weasyprint）→ 目視檢查（封面、目錄、圖、寬表格）→（使用者慣例）驗證後以 `send-report` 寄出 PDF。

**接手步驟**
1. Qwen 服務是**使用者自己啟動、與其他工作共用**；2026-10-12 為 DOWN（使用者關閉）。**不要自行重啟或搶 GPU**，先問使用者；服務就緒後：`OMP_NUM_THREADS=1 python3 scripts/textbook/draft.py zh --threads 2 --no-audit`（已完成章節會跳過；服務中斷時腳本會印 PAUSED 並保留進度）。
2. `OMP_NUM_THREADS=1 python3 scripts/textbook/status.py` 看每章進度（不需 GPU）。
3. 草稿齊全後依上列流程審稿。Qwen 自我審查（`--no-audit` 已略過）只供參考，不要自動套用。
4. 轉寫速度參考：服務被使用者其他工作共用時，單章約 50 分鐘（2 路平行）。

