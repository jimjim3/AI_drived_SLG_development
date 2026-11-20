# 授權與資料來源說明

狀態:**暫定,尚未做最終授權決定**(2026-11-14 負責人決定專案為免費開源;資料授權待定)。

| 內容 | 位置 | 授權狀態 |
|---|---|---|
| 程式碼 | `src/`、`scripts/`、`tests/` | MIT([LICENSE](LICENSE)) |
| 設計與評測文件 | `docs/*.md` | 暫同程式碼(MIT);待決定是否改 CC BY |
| 劇情文本、事實卡 | `src/slg/narrative/`、`docs/narrative/` | 原創撰寫,**尚未對照原典複核**;待定 |
| 美術(肖像、城池、戰鬥場景、圖示) | `src/slg/web/static/assets/`、`art_work/`、`docs/art/` | 由 Qwen-Image 等模型生成;**模型與素材授權條款尚未逐項核對**,發布前必須確認 |
| 模型生成的資料庫 | `data/sanguo/`(含 `ext/`) | 內容由 LLM 生成,全部 `unverified`,**不保證史實正確**;引擎未使用;授權待定 |
| 光榮參考值 | `data/sanguo/koei_stats.json`、`koei11_reference.json`、`koei_city_sizes_agy.json`、`raw*` | **來源為光榮《三國志》系列的數值或其網路整理,屬灰色地帶(見 [docs/PRIOR_ART.md](docs/PRIOR_ART.md) §D)。僅供開發期對照,不得隨遊戲或公開發行版散布。** 公開發行前須從發行版中移除,遊戲內數值改為自訂 |
| 引擎內 42 名武將的能力值 | `src/slg/engine/initial_state.py` | 最早期手填,無出處;目前與光榮數值不同(自成量尺),但發行前仍須依史傳重新訂定並記錄出處 |
| 教科書草稿 | `docs/textbook/` | 由 LLM 草擬、總編輯修訂;草稿階段 |

## 發布前待辦(M2 之前完成)
1. 決定資料與美術的授權(建議:資料 CC BY-SA 4.0、美術 CC BY 4.0,視素材模型條款而定)。
2. 逐項核對美術生成模型的授權條款與可商用範圍。
3. 從發行版移除光榮參考檔,武將數值改為自訂並記錄出處。
4. 史實資料逐劇本核實後才標 `verified`。
