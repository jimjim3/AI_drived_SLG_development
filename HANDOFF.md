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
