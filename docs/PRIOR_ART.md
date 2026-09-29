# 可參考 / 可改造的開源專案

> 調查日期：2026-09。授權資訊請在 fork 前自行再次確認；本文不構成法律意見。

## A. 三國題材

| 專案 | 技術 | 授權 | 評估 |
|---|---|---|---|
| [JuQiang/Rotk2_Python](https://github.com/JuQiang/Rotk2_Python) | Python + Pygame | **未標示** | ⚠️ **不建議當基底**。以 IDA 逆向原版 DOS 遊戲，且讀取原版 KOEI 資料檔；戰爭與 AI 部分尚未實作；星數很少、提交紀錄僅 9 筆。開源再發佈有版權風險。 |
| [luiges90/ZHSAN3](https://github.com/luiges90/ZHSAN3)（中華三國志重製版 3.0） | Godot / GDScript | **GPL-3.0**（`Images/PersonPortrait` 除外） | ✅ 授權清楚、仍在開發、武將制系統完整。可研究其資料結構與規則；若直接 fork，你的專案也須採 GPL-3.0，且需替換頭像。 |
| [luiges90/ZHSAN2](https://github.com/luiges90/ZHSAN2) | — | — | 已封存（2023），可作歷史參考。 |
| [delkana/threekingdoms](https://github.com/delkana/threekingdoms) | 純 HTML/JS + Node | 未見 LICENSE 檔 | 內容完整（23 勢力、58 城、真實地理、六角戰鬥），**AI 已有人格分類**（schemer/honorable/treacherous/cautious…）與戰區規劃——非常適合當「規則 AI 對照組」的設計參考。使用程式碼前需向作者取得授權。 |
| [alberthsiao/qunxiong-zhulu](https://github.com/alberthsiao/qunxiong-zhulu)（群雄逐鹿） | 單一 HTML/JS | 未見 LICENSE 檔 | 光榮式、190+ 武將、程式生成 SVG 頭像、有自動化模擬測試。同上，需確認授權。 |

## B. 已經在做「LLM 玩策略遊戲」的專案（最值得先讀）

| 專案 | 重點 |
|---|---|
| [CIVITAS-John/vox-deorum](https://github.com/CIVITAS-John/vox-deorum)（[論文 arXiv:2512.18564](https://arxiv.org/abs/2512.18564)） | 文明 V：**LLM 只負責宏觀戰略，微操交給原本的演算法 AI**，能跑完 400 回合且勝率與原 AI 持平。幾乎就是本專案「分層」理念的實證。 |
| [fuxiAIlab/CivAgent](https://github.com/fuxiAIlab/CivAgent)（MPL-2.0） | 基於開源 [Unciv](https://github.com/yairm210/Unciv) 的 LLM 數位玩家，含**自然語言外交**（Discord 介面）。 |
| [CivRealm](https://arxiv.org/abs/2401.10568)（ICLR 2024） | Freeciv 上的 RL / LLM 代理環境；結論是 LLM 在完整遊戲中仍很吃力——提醒我們要靠分層與規則 AI 補位。 |

## C. 通用回合制引擎（非三國）

- **Freeciv**（GPL）、**FreeCol**（GPL）、**Unciv**（MPL-2.0）：成熟、可 headless，但換成三國題材的工作量大；適合先拿來「驗證 AI 架構」，不適合當最終產品。

## D. 版權與專利重點

- **規則與機制**：著作權不保護（idea/expression 二分）。**專利**則可能保護機制，但 1980–90 年代遊戲的專利（期限約 20 年）早已過期；新機制仍建議做簡單專利檢索。
- **受保護的**：原作程式碼、圖像、音樂、文字、劇本資料檔。「老遊戲 / Abandonware」**仍有版權**。
- **《三國演義》原文、陳壽《三國志》**：公有領域，可自由使用人物與事件。
- **KOEI 的武將數值表**：屬於有爭議的灰色地帶（編輯著作 / 資料庫權依法域而異）。最安全的做法是**自己訂數值**（例如由演義事蹟以規則或 LLM 推導），不要照抄。
- **美術**：AI 生成或程式生成頭像，並在 README 註明來源與授權。
