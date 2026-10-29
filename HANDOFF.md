# HANDOFF — AI-Driven SLG（更新於 2026-10-26）

## 狀態一句話
引擎、LLM 勢力代理、評測、劇情文本、網頁介面皆可運作並已推送（分支 `claude/ai-hierarchical-slg-game-fl3ojj`，HEAD `5623303`，**435 個測試全過**，工作區乾淨）。網頁預設規則 `softer_pool2_far`（遠路攻城 ×0.75），AI 對手會進攻、戰報有敘事句。**仍然沒有真人試玩過、沒有在真實瀏覽器驗證畫面**。

## 快速開始（換機器時）
```bash
git clone git@github.com:jimjim3/AI_drived_SLG_development.git && cd AI_drived_SLG_development
git checkout claude/ai-hierarchical-slg-game-fl3ojj
python3 -m unittest            # 需 Python 3.10+；教科書製圖測試另需 matplotlib（其餘僅用標準庫）
scripts/serve.sh               # 網頁介面 http://127.0.0.1:8080/ ；部署與試玩方式見 deploy/README.md
```
金鑰與網址**只放環境變數**（`NVIDIA_API_KEY`、`SLG_QWEN_URL`、`SLG_ACCESS_TOKEN`…），不在 repo 內。

## 先讀
README.md（較舊）→ deploy/README.md → docs/EVALUATION.md（**第 11、12 節是最新實驗**）→ docs/narrative/README.md → 本檔。

## 最近完成了什麼
- **進攻局**：`advantage` 仍是劉備占優（舊評測不變）；`advantage:faction_N` 讓第 N 家占優，網頁選進攻局時自動讓**玩家所選君主**占優（`resolve_scenario`）。
- **劇情文本**（`src/slg/narrative/`）：42 武將、3 君主、9 城、事件模板、6 種「劇本×君主」開場；有測試對照引擎資料。事實卡在 `docs/narrative/officer_fact_cards.json`，**尚未對照原典複核**。事件模板還沒接進結算畫面。
- **網頁**：開局簡報、城池介紹、武將傳略、年季；對手選項 rule/demo/nim/qwen/gemini；每分頁獨立對局；`SLG_ACCESS_TOKEN` 保護。
- **評測工具**：`--http-retries/--http-timeout/--min-interval`（免費層限速與逾時）、`--siege-verdict`（引擎判定附在勝算比旁）、最低忠誠／最高冷落診斷。
- **修掉的 bug**：驗證器遇到非數值參數會讓整個評測崩潰（現在拒絕並回報）。

## 實驗結論（細節與數字見 EVALUATION.md 第 11、12 節）
1. **出征判定**（`--siege-verdict`）對會冒進的模型很有效：Super 長局 40 回合 N8→N9 兵力差 -8745→+2718；Ultra N4→N5 -115→+1592；對本來就守紀律的 Qwen 沒有差別。
2. **Qwen3.8-27B**（Colab Q4 量化）最守紀律，攻城成功率高；Q4 與 Q8 表現相近。
3. **NIM**：Super 約 6 秒／次，Ultra 品質稍好但尖峰時段常 503；都要重試。兩個 NIM 對手一回合約 27 秒（網頁實測）。
4. **忠誠／冷落機制在 ≤40 回合的真實 LLM 對局中不會觸發**（最低忠誠 59–68，門檻 50／35）。使用者決定先不調整。
5. **對手不出兵的根因是戰鬥平衡，不是模型**（EVALUATION.md §13）：預設情境 240 個勢力回合裡從來沒有勝算比 ≥1.0 的目標（最高 0.70），Qwen 加進取個性也不出兵是理性的。守方戰力約為攻方的 1.5–1.7 倍，且出征只能抽單一城池的兵力。用 `scripts/attack_opportunities.py` 量測調整前後的效果。

## 待辦（依優先序）
1. **瀏覽器端到端驗證並截圖**（需安裝 playwright；`scripts/e2e_web.py` 已備好），確認戰報敘事句、開場簡報版面。
2. **真人試玩幾局**，記錄無聊、卡住、看不懂之處（目前完全沒有這方面資料）。
3. **部署到 SSH 伺服器**（`deploy/README.md`、`deploy/slg-web.service`；需要使用者提供登入方式與 `SLG_ACCESS_TOKEN`）。
4. 平衡：東南角（建業／吳郡／會稽）勢力幾乎全勝（原地圖 Qwen 4/4、Super 8/10、Ultra 5/5；§14–§17），已排除座位、入口數、起始資源、武將能力，剩「位置」本身。使用者說不平衡屬正常，有機會再看。
5. 對照原典複核事實卡與武將能力值（能力值自最早提交起手填、無出處）。
6. 尚未接入的事件模板：忠誠警告／稱讚、饑荒、滅國（引擎無對應事件）。
7. 補評測：各組只有 3–10 個種子、單一模型，無信賴區間。NIM 的 Nemotron 3 Super 自 2026-10-20 起對本帳號回傳 404，目前用 Ultra。

## 近期已完成（2026-10-19～22）
戰鬥規則可切換（`engine/combat.py`，預設 `v2`；網頁預設 `softer_pool2`）；規則 AI 改用引擎勝算估計出征；系統提示加入金幣花費說明（被拒指令約 -35%）；戰報敘事句（`web/payload.py::story_lines`）；地圖變體 `+sun2`／`+swap13`／`+swapres13`／`+swapoff13`（僅供實驗）。

## 已知缺陷
rest 比例約 47%；faction_2 的宛城／漢中武將不與任何敵城相鄰故無法出奔；`evaluate` 整組結束才寫檔（中止時會寫出已完成的種子）；對局都在記憶體裡，伺服器重啟就沒了；網頁沒有存檔。

## 操作知識（這台 Mac；與舊伺服器不同）
- 沒有本機 Qwen 與 GPU：Qwen 由使用者的 Colab 提供（每天約 2 小時，網址每次不同，需使用者貼新網址；`reasoning_effort:none` 才能關閉思考）。
- 助手 AI 順序：**NIM 優先**（免費），agy 只在 NIM 做不到時才用（會消耗 Antigravity 額度）。NIM 金鑰在 `~/.local/state/local-llm/nvidia-api-key`，**不要放進命令列或檔案**。
- 這台 `git`、`python3` 需 `DEVELOPER_DIR=/Library/Developer/CommandLineTools`（Xcode 授權未接受）；`~/.zshenv` 已設定。推送用 SSH 位址（HTTPS 沒登入）。
- 驗收慣例：不採信 worker 自述；重跑測試；NIM／agy 的輸出只當線索，會改變結論的宣稱要自己抽查（本專案劇情文本就抓到多處捏造的史實）。

---
# 舊交接（2026-10-11／12，保留供查；其中 Qwen 伺服器與路徑指的是舊的 Linux 機器）


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


## 戰鬥規則變體（2026-10-19）
`engine/combat.py` 提供可切換規則；預設 `v2` 不變。`softer_pool2` 下 Qwen 對手會真正進攻（見 docs/EVALUATION.md §14），但孫權（地形）4/4 勝，故未設為預設。**網頁伺服器預設用 `softer_pool2`**（讓 AI 對手會進攻）；要回原規則用 `SLG_RULES=v2` 或 `--rules v2`。評測腳本預設仍是 `v2`。待辦：處理孫權地形優勢→再決定預設；規則 AI 仍不會進攻。
