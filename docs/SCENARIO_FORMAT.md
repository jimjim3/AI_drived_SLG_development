# 劇本格式 v1(Scenario Format v1)

狀態:**規格加驗證器加載入器已完成**(`src/slg/engine/scenario.py`、`tests/test_scenario.py`)。**引擎尚未使用它**:內建劇本仍由 `initial_state.py` 建立;網頁、評測還沒有「選劇本檔」的入口(M1 工作,見第 6 節)。

## 1. 目標
- 一個 JSON 檔 = 一個完整劇本(地圖、勢力、城池數值、武將、事件、勝利條件)。
- 任何人不改程式就能做新劇本;錯誤要被驗證器說清楚,不能靜默吞掉。
- 引擎還不會做的欄位(事件、中立城、其他勝利類型),要嘛只驗形狀並原樣帶進中繼資料,要嘛明確拒絕,**不假裝支援**。
- 內建的 9 城劇本能匯出成此格式,載入後與原本的 `GameState` 完全相同(測試保證)。

## 2. 頂層欄位
| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `format` | 整數 | 是 | 固定 `1` |
| `id` | 字串 | 是 | 小寫英數與底線,例:`guandu_200` |
| `name_zh` | 字串 | 是 | 劇本名 |
| `year` | 整數 | 是 | 開局西元年 |
| `summary_zh`、`opening_zh` | 字串 | 否 | 簡介、開場白 |
| `verification` | 字串 | 是 | `unverified`(模型生成未核實)、`verified`(人工對照史料)、`game_design`(純遊戲設計,不主張史實) |
| `sources` | 陣列 | 否 | `verified` 時列出出處(書名、卷、人工核對者) |
| `rules` | 字串或 null | 否 | 建議的規則集名(須在 `combat.RULESETS`) |
| `map` | 物件 | 是 | 見第 3 節 |
| `factions`、`cities`、`officers` | 陣列 | 是 | 見第 4 節 |
| `events` | 陣列 | 否 | 見第 5 節 |
| `victory` | 物件 | 是 | 目前只支援 `{"type":"most_cities","turns":N}` |

## 3. 地圖 `map`
```json
{"cities": [{"id": "xuchang", "name_zh": "許昌", "pos": [7.0, 4.8]}],
 "edges":  [["xuchang", "chenliu"]]}
```
- 城 id 唯一;`pos` 是畫面座標 `[x, y]`(單位由前端決定)。
- 邊是無向的,不可重複、不可自環。
- **地圖必須連通**,否則驗證失敗。
- 保留(尚未使用):邊的類型(道路、山道、水路)、關隘、城規模、地形。加入時會以新欄位出現,不改現有欄位意義。

## 4. 勢力、城池、武將
**勢力** `factions[]`:`id`、`name_zh`、`capital`(必須是該勢力擁有的城)、`playable`(布林)。至少 2 個勢力。每個勢力至少擁有 1 城、1 名武將。

**城池狀態** `cities[]`(每個地圖城恰好一筆):`id`、`owner`(勢力 id)、`agriculture`、`commerce`、`defense`、`gold`、`food`、`troops`,皆為非負整數。

**武將** `officers[]`:`id`、`name_zh`、`faction`、`city`、`politics`、`war`、`leadership`(0–100)、選填 `loyalty`(預設 80)、`ambition`(預設 50)。**武將所在城必須屬於其勢力。**

## 5. 事件 `events[]`(目前只驗形狀)
`{"id": "e1", "turn": 3, "text_zh": "……"}`:`id` 唯一、`turn` ≥ 1、`text_zh` 非空。條件觸發(人物在場、城池歸屬)與效果會在 M1「史實事件引擎」定義,屆時以 `conditions`、`effects` 欄位擴充;載入器目前把事件原樣放進 `ScenarioMeta.events`。

## 6. 勝利 `victory`
- 目前:`most_cities`(到 `turns` 回合時城池最多者勝,同現行規則)。
- 保留、**驗證器會拒絕**:`capture_capital`(攻陷指定首都)、`unify`(占領比例)。M1 實作時再開放。

## 7. 驗證器與載入器
```python
from slg.engine import scenario
problems = scenario.validate(doc)          # 全部問題的清單,空 = 合法;不會因壞輸入而拋例外
state, meta = scenario.load("data/scenarios/default_v1.json")   # 驗證後建出 turn=0 的 GameState 與 ScenarioMeta
```
載入器把鄰接表的相鄰城依字母排序(確定性)。測試確認內建劇本以此載入後,同種子對局結果與原本相同,表示目前引擎行為不依賴相鄰城順序。

## 8. 已知缺口(從現有資料庫轉成 v1 之前必須處理)
拿 `data/sanguo/ext/scenarios_fixed/e200.json`(官渡)對照,要變成可載入的 v1 劇本還缺:
1. **城池數值**:草稿只有「誰擁有哪些城」,沒有農業、商業、城防、金、糧、兵。需要由城規模加勢力強度推導的規則(M1)。
2. **武將能力值與 id**:草稿只有姓名、所在城、職稱;能力值要自訂(NOTICE.md:不可照抄光榮)。草稿的 74 筆補充資料是模型估計,未核實。
3. **中立城**:官渡草稿有 15 座中立城,**引擎目前沒有「無主城」**。建議做法:建立一個沒有決策者的「在野勢力」,由固定規則守城、不外交、不擴張。這是 M1 的引擎工作,驗證器目前明確拒絕 `owner: null`。
4. **規模**:官渡草稿袁紹 29 城、曹操 33 城,遠超目前 9 城;M1 先決定要用精簡版(約 20 城,合併相鄰小城)還是完整版,並確認規則 AI 和 LLM 提示詞在大地圖下的行為與成本。
5. **前端寫死的部分**:`web/payload.py` 的 `CITY_POS`、`static/map.js` 的 `CITY_POS` 與 `FACTION_INFO`、`FACTION_IDS = faction_1..3`。要改成由 `ScenarioMeta` 提供座標、勢力名與顏色。
6. **勢力 id**:引擎多數地方以 `sorted(state.factions)` 運作,理論上支援任意 id,但尚未用非 `faction_N` 的 id 實測。

## 9. M1 接入步驟(建議順序)
1. `Session`/`App.new` 與 `selfplay.py` 接受 `scenario_file`,用 `scenario.load` 取代 `build_initial_state`。
2. 前端座標與勢力色改由伺服器提供(payload 帶 `map` 與 `factions`)。
3. 實作在野勢力(中立城)。
4. 實作 `capture_capital`、`unify` 勝利判定。
5. 做出第一個非內建劇本(官渡精簡版),用 `validate` 把關,自我對弈 20 局檢查平衡。
6. 事件引擎。
