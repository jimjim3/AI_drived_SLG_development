# 網頁介面規格 v0.1（2026-10-13）

決議背景見 docs/memos/2026-10-13-web-ui-direction.md。目標：玩家與 AI 完全同條件，介面只是 `FactionAgent` 的一種輸入方式。

## 1. 原則
1. **引擎是唯一真相**：前端不算任何規則；合法行動、攻城勝率估計都由後端回傳（`generate_legal_actions`、`estimate_siege_ratio`）。
2. **玩家 = FactionAgent**：後端 `HumanFactionAgent.decide(view)` 阻塞等待前端送來的 `FactionPlan`（orders、chronicle、next_cast），其餘與 AI 同走驗證、迷霧、關注名單上限（CAST_LIMIT=6）。
3. **玩家只看得到 `FactionView`**：不暴露全域狀態（否則比 AI 多資訊）。觀戰模式例外，需明確標示並關閉玩家席位。
4. 被引擎駁回的命令回傳 `feedback`，下一回合顯示（與 AI 相同）。
5. 無建置工具、無外部 CDN 依賴：純 HTML/CSS/ES module，離線可跑。

## 2. 架構
```
瀏覽器 (static/) ⇄ HTTP+SSE ⇄ server.py (標準庫 http.server) ⇄ Game(引擎) ⇄ AI 勢力 agents
```
- 後端模組：`src/slg/web/server.py`（路由）、`session.py`（一場遊戲、執行緒、HumanFactionAgent）。僅用標準庫。
- 一個 session 在背景執行緒跑 `Game.step()`；輪到玩家勢力時 `HumanFactionAgent` 發出 `awaiting_input` 事件並等待 `POST /plan`（逾時視為全員休息並記錄）。
- 事件推送用 Server-Sent Events（`GET /api/events`），避免依賴 websocket 套件。

### API（JSON）
| 方法 路徑 | 說明 |
|---|---|
| POST `/api/new` `{scenario,seed,player_faction,ai:{faction_id:"rule"\|"qwen"\|"gemini"},turns}` | 建立遊戲，回傳 `session_id` |
| GET `/api/state` | 玩家的 `FactionView.to_dict()`＋ `map`（城座標/鄰接/歸屬，僅可見資訊）＋ `legal`（每位 cast 武將的 `format_legal` 結構化版） |
| POST `/api/plan` `{orders:[{officer,action,params}],chronicle,next_cast:[...]}` | 提交本回合計畫 |
| GET `/api/events` (SSE) | `turn_start`、`awaiting_input`、`resolution`（本回合事件，已過迷霧）、`game_over` |
| GET `/api/replay/<id>` | 回合日誌（`TurnLog`），供回放 |
| POST `/api/estimate` `{city,target,troops}` | 回傳 `estimate_siege_ratio` 結果（與 AI 看到的偵察資訊同源） |

## 3. 畫面（參考 Rotk2_Python 版面，自行實作）
```
┌───────────────┬──────────────────────────┐
│ 年月季節（回合）│ 標頭：所在城／君主／官職／頭像   │
│  地圖（SVG）    ├──────────────────────────┤
│  城=可點節點    │ 資訊面板（依選單切換）          │
│  顏色=勢力      │  城資訊／武將列表／能力表／情報  │
│  迷霧=灰        ├──────────────────────────┤
│               │ 指令列（編號選單＋鍵盤輸入）     │
└───────────────┴──────────────────────────┘
```
畫面清單：
1. 標題／選單（新遊戲、載入回放、離開）。
2. 選擇君主與情境（`default`／`advantage`）、設定各 AI 後端。
3. 主畫面（上圖）。
4. 派遣面板：選武將（只列 cast 內，最多 6）→ 選行動（只列該武將的合法行動）→ 填參數（範圍來自 `ParamSpec`）→ 加入命令清單；清單顯示衝突（同城金錢預算，見下）。
5. 攻城面板：選出兵城、目標、出兵數；顯示偵察得到的勝率估計。
6. 關注名單：下一回合 `next_cast` 勾選（上限 6），顯示各武將忠誠／冷落警示（引擎給的欄位，不自行推論）。
7. 回合結算：事件逐條顯示、被駁回命令與理由、AI 勢力的 chronicle（以「奏摺」呈現）。
8. 結束畫面：勝負（城數、總兵力）與回放入口。

互動：全程可鍵盤操作（數字選單，沿襲原版習慣）也可滑鼠點擊。

## 4. 已知引擎限制須在介面體現
- 同城金錢競爭：約 20% 命令因同城預算被駁回 → 派遣面板即時顯示「該城剩餘金額」，並在加入命令時預扣（純顯示；最終以引擎驗證為準）。
- 戰爭迷霧：非鄰接敵城不顯示兵力。
- 關注名單：未被關注武將會被規則 AI 代管（顯示為「自動」）。

## 5. 檔案配置
```
src/slg/web/{__init__,server,session,human_agent}.py
src/slg/web/static/{index.html,app.js,map.js,panels.js,style.css,assets/}
tests/test_web_*.py
```
`assets/` 先放程式產生的 SVG／佔位圖；原創頭像等待 GPU（見 memo）。

## 6. 驗收
1. `python3 -m unittest -q` 全過，含新測試：HumanFactionAgent 阻塞／逾時／非法命令駁回；`/api/state` 不含迷霧外資訊（以非鄰接敵城兵力欄位不存在斷言）；SSE 事件順序；同 seed 同命令序列重現同結果。
2. 玩家用「全員休息」與規則 AI 席位的對局，結果與 headless 同席位同 seed 的 `run_headless` 一致（鎖定同條件）。
3. 一個 headless 瀏覽器腳本（playwright，若可用）走完：新遊戲→派遣→提交→看到結算→結束；截圖存檔。
4. 靜態頁在 360px 與 1280px 寬都不水平捲動。

## 7. 分工
| 件 | 誰 | 備註 |
|---|---|---|
| 後端 session／human_agent／測試 | 主管（我）寫介面與驗收；樣板可派 agy | 涉及引擎邊界與公平性，我審 |
| 前端 HTML/CSS/JS 起草 | agy（雲端，公開專案，可外送） | 依本規格，我驗收並跑瀏覽器截圖 |
| 地圖 SVG、UI 框 | 程式產生 | 可先做 |
| 頭像、標題圖 | qwen-image-lab／agy | 待 GPU |
