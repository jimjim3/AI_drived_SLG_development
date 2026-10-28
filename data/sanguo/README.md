# 三國資料庫（累積中，測試階段**不被遊戲引擎使用**）

用途：為日後擴充城池、地圖、武將預先累積資料。目前引擎仍只用 `src/slg/engine/initial_state.py` 的 9 城 42 將。

| 檔案 | 內容 |
|---|---|
| `cities.json` | 城池／州郡治所：id、名稱、州、概略座標、地形標籤、戰略定位、相鄰城池 |
| `officers_<批次>.json` | 武將：id、名、字、陣營沿革、職能標籤、籍貫城、生卒（概略）、一句話定位、能力**估計** |
| `raw/` | agy／NIM 的原始輸出（除錯用） |
| `../../scripts/build_sanguo_dataset.py` | 產生器（呼叫 agy `ask`，無工具、僅文字） |
| `../../scripts/validate_sanguo_dataset.py` | 機械驗證：id 唯一、相鄰對稱、引用的城存在、欄位型別 |

## 可信度規則
- 所有能力值都是 `stats_estimate`，來源標註為模型記憶、**未經查證**（`verification: "unverified"`）。要作為遊戲數值前，必須對照光榮《三國志》系列公開資料並改成 `verified`。
- 座標為概略，用於相對位置，不可當地理資料。
- 與遊戲內現有 42 將重疊者保留相同 id（`in_game: true`），遊戲內數值仍以 `initial_state.py` 為準。

## 目前內容（2026-10-28 第一版）
40 城、186 位武將（魏 55／蜀 45／吳 45／群雄 50，跨批次重複者已合併為一筆並併入 `faction_path`），其中 42 位與遊戲內名單重疊（`in_game: true`，id 已對齊 `initial_state.py`）。機械驗證 0 問題。與遊戲內 42 將比對，武力估計平均差 6.7（最大差 26：程昱），**但這只代表兩份都是人工／模型印象值彼此相近，不代表正確**。

重建：`python3 scripts/build_sanguo_dataset.py all`（會覆蓋）；只做合併與對齊：`... postprocess`；驗證：`python3 scripts/validate_sanguo_dataset.py`。
