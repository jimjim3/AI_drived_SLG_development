# 試玩與部署

網頁介面是純標準庫的 Python 伺服器（無需安裝套件），靜態頁無建置步驟。**所有狀態都在記憶體裡**，重啟就沒有進行中的對局；金鑰與網址只放環境變數，不進 repo。

## 先看這三點（安全）
1. 預設只監聽本機（`127.0.0.1`）。要讓別台機器連進來必須設 `SLG_ACCESS_TOKEN`，否則伺服器拒絕啟動（`--insecure` 可強制，不建議）。
2. 設了 `SLG_ACCESS_TOKEN` 後，第一次用 `https://網址/?token=<密碼>` 開啟，之後靠 cookie；API 也可用 `Authorization: Bearer <密碼>`。`/healthz` 例外，用來檢查服務是否活著。
3. 伺服器端的金鑰（NIM、Gemini）會被每一局使用。**不要把沒有密碼的伺服器公開**，否則任何人都能花掉你的額度。

每個瀏覽器分頁各有一局（上限 8 局，超過時最久沒用的會被丟掉）。

## 環境變數
| 變數 | 用途 |
|---|---|
| `SLG_ACCESS_TOKEN` | 存取密碼（非本機綁定時必填） |
| `SLG_HOST`、`SLG_PORT` | 監聽位址與埠（預設 `127.0.0.1`、`8080`） |
| `NVIDIA_API_KEY` | 啟用設定畫面的 **nim** 對手（NVIDIA 免費額度；預設模型 `nvidia/nemotron-3-super-120b-a12b`，可用 `SLG_NIM_MODEL` 換） |
| `SLG_QWEN_URL` | 啟用 **qwen** 對手，例如 Colab 上 Qwen 的 `https://xxx.trycloudflare.com/v1` |
| `SLG_QWEN_MODEL` | 預設 `qwen3.8:27b`（Ollama 標籤）；跑 llama.cpp 則填它的別名 |
| `SLG_QWEN_EXTRA_BODY` | 覆寫 Qwen 的請求附加欄位（預設同時關閉 Ollama 與 llama.cpp 的思考） |
| `GEMINI_API_KEY` | 啟用 **gemini** 對手（耗你的雲端額度） |

沒設的選項不會壞，只是選了之後該 AI 會連線失敗並退回規則 AI。**rule**（規則 AI）與 **demo** 永遠可用、離線。

## 方式 A：直接在本機試玩（最簡單）
```bash
scripts/serve.sh              # 或：PYTHONPATH=src python3 -m slg.web.server 8080
# 瀏覽器開 http://127.0.0.1:8080/
NVIDIA_API_KEY=... scripts/serve.sh   # 要玩 nim 對手時
```
需要 Python 3.10 以上。

## 方式 B：自己的 SSH 伺服器
**最安全：不開任何公開埠，用 SSH 轉發**（不需要密碼，因為只綁本機）：
```bash
# 伺服器上
git clone <repo> && cd AI_drived_SLG_development && scripts/serve.sh
# 你的電腦上
ssh -L 8080:127.0.0.1:8080 <使用者>@<伺服器>      # 然後開 http://127.0.0.1:8080/
```
**常駐**：用 `deploy/slg-web.service`（systemd 使用者單元），金鑰放 `~/.config/slg-web.env`（權限 600）。
**要給別人用**：放在反向代理（nginx、Caddy）的 HTTPS 後面，設 `SLG_ACCESS_TOKEN`；不要直接把埠開到網際網路。
伺服器有 GPU 時，可在同一台跑 llama.cpp 或 Ollama，`SLG_QWEN_URL=http://127.0.0.1:<埠>/v1`，延遲最低。

## 方式 C：Colab（臨時公開網址）
開一個 **CPU** 執行階段，把 `deploy/colab_serve_game.py` 整份貼進一個儲存格執行（先在 Secrets 放好 `GITHUB_TOKEN`（若 repo 為私有）、`NVIDIA_API_KEY`、`SLG_QWEN_URL`）。它會複製 repo、啟動伺服器、用 Cloudflare 建立通道，並印出**帶密碼的連結**。關掉儲存格網址就失效；網址每次都不同。Qwen 可以另開一個 GPU 執行階段（你現有的筆記本），把它印出的 `…/v1` 貼進 `SLG_QWEN_URL`。

## 方式 D：GitHub Codespaces
repo 已有 `.devcontainer/`。到 GitHub 的 repo 頁按 Code → Codespaces → Create，容器啟動後會自動執行伺服器並轉發 8080（轉發網址預設只有你自己能開，由 GitHub 驗證身分）。金鑰請設在 Codespaces 的 Secrets（`NVIDIA_API_KEY` 等），它們會成為環境變數。有免費時數上限。*（此方式我沒有實際測過。）*

## 已知限制
- 每一回合，每個 LLM 對手各呼叫一次模型。**實測**：兩個 NIM 對手跑完一回合約 27 秒；Colab Qwen 每次呼叫約 17 到 20 秒，兩個對手估計約 35 到 40 秒（未實測整回合）。畫面會顯示「各勢力正在決策」。只想快速試玩可選 rule。
- 沒有帳號系統，沒有存檔；伺服器重啟，所有對局消失。
- 只有一把共用的 NIM 金鑰，多人同時玩會共用同一個限速額度。
- 還沒有真人試玩過：平衡、好不好玩都沒有數據。

## 換伺服器
repo 本身不依賴任何機器：`git clone` 後執行 `scripts/serve.sh` 即可。需要帶走的只有環境變數（金鑰、`SLG_QWEN_URL`）。目前進度與待辦見 `HANDOFF.md`。
