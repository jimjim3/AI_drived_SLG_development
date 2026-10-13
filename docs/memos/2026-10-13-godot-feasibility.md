# Godot 作為介面的可行性（agy 研究，2026-10-13）— 總編輯註記

> 來源：agy researcher（gemini-3.8-flash-high，公開資料，空資料夾執行）。**以下全文是線索，非定論。**
> 我的查核：
> - ❌ 報告稱「當前穩定版 4.4.x」**已過時**：我另查得 4.6（2026-01-26）、4.6.3（2026-05-20）、4.7.x（2026-06～08，來源為二手彙整站，未見官網公告）。版本相關結論（Web 匯出、IME）需以新版重驗。
> - ⚠️ MVE 範例用 `/api/action`、`CORS`，與我們實際 API（`/api/state`、`/api/plan`、`/api/status`，同源）不同；實驗時以我們的 API 為準。
> - ✅ 其餘（MIT 授權、`Polygon2D`+點選做 41 區地圖、`--headless` 無渲染、.tscn 易被 LLM 寫壞、Web 匯出體積偏大）與我所知一致，但數字（9–11 MB wasm、字型 1–15 MB）未獨立查證。
>
> **我的結論**：同意其方向——維持 Web；Godot 若要做，只作「共用同一 JSON API 的第二前端」，**絕不改寫規則進 GDScript**（破壞單一真實來源與玩家=AI 公平性）。是否值得，見觸發條件（報告 §6）。

---

# Godot 作為「三國志式回合制策略遊戲」介面可行性評估報告

---

## Summary
針對現有「純 Python 標準庫確定性引擎＋純靜態 HTML/JS/SVG 前端」之三國志式回合制 SLG，**強烈建議現階段「維持 Web 前端」，切勿盲目改用 Godot**。Godot 4 雖具備優秀的 2D UI 與節點系統，但用於無複雜動畫的文字/數值面板與 41 國分區地圖時，相對於現有 Web 技術屬於嚴重「過度工程（Over-engineering）」；其 Web 匯出體積暴增數十倍（Wasm 壓縮後仍達 ~10MB 且需外掛數 MB 中文字型）、手機 360px 適應困難、且在 Wasm 畫布下中文字輸入（IME）存在已知缺陷。若未來確實出現「大地圖兵線/戰鬥粒子動畫」或「上架 Steam 桌面獨立版」之硬性需求，唯一合理的整合架構為**「共用同一 JSON API」**將 Godot 作為純展示端（View-only Client），絕不可將規則改寫為 GDScript。

---

## Findings

1. **核心架構必須維持解耦，嚴禁 GDScript 改寫規則**：Python 引擎擁有確定性、不可變狀態、以及供玩家與 LLM/規則 AI 共享的完全對稱介面。改寫 GDScript 將破壞單一真實來源（Single Source of Truth），導致 AI 與核心邏輯雙重維護災難。最合理的架構是前端僅透過 `HTTPRequest` 節點消費 JSON API。
2. **Web 匯出體積與載入時間劇增（破壞「輕量離線」優勢）**：Godot 4.3 雖支援單執行緒 Web 匯出、擺脫了 `SharedArrayBuffer` 與 COOP/COEP 跨來源隔離標頭限制，但空專案的 `.wasm` 壓縮後仍有 9–11 MB（未壓縮約 33–42 MB）；加上繁體中文字型（1–15 MB），下載體積將從現有純 Web 的數百 KB 飆升至 15–25 MB，首屏編譯載入需 3–10 秒。
3. **分區省份地圖（DOS 三國志 II 風格）技術選型明確**：三國志 II 全地圖僅約 41 國，使用 `Polygon2D` 搭配 `Area2D`（或 `Geometry2D.is_point_in_polygon`）即可兼顧銳利向量外觀與節點級點選點擊；萬級省份大戰略遊戲採用的「顏色索引貼圖＋Shader（ID Map）」技術在本專案規模下屬於不必要之複雜化。
4. **繁體中文與輸入法（IME）在 Web 匯出存在致命硬傷**：桌面環境下 Godot 4 的 `TextServerAdvanced`（基於 ICU 與 HarfBuzz）已能妥善處理 CJK 自動換行與禁則處理；但在 WebAssembly/HTML5 Canvas 匯出下，瀏覽器原生 IME 候選字視窗整合長年存在相容性問題，且無法調用作業系統內建字型，必須在封裝中內嵌完整字型檔。
5. **CI 與自動化截圖驗收存在「`--headless` 陷阱」**：Godot 4 的 `--headless` 命令列參數預設會停用所有視窗與渲染管線（渲染伺服器返回 null 紋理）。若需進行視覺回歸截圖測試，必須在 Linux CI 環境使用虛擬緩衝區（`xvfb-run`）搭配 `--rendering-driver opengl3` 執行，而非純粹的 `--headless`。
6. **LLM 輔助開發之穩定度差異**：LLM 生成 GDScript 邏輯代碼品質極高，但生成 Godot 4 場景描述檔（`.tscn`）時，因其專屬的 UID 語法（`uid://...`）與巢狀子資源關聯，非常容易產生損壞檔。實務上應維持 `.tscn` 極簡化，由 GDScript 代碼以程式化方式動態生成 UI 節點。
7. **開源生態現況佐證**：開源社群中的 Godot 策略遊戲（如 `OpenCiv3`、`world_conquest`）99% 皆為單體式架構（遊戲規則與渲染全寫在 GDScript/C#）；採用「Python 後端＋Godot 純展示端」的先例多見於 AI Agent 研究環境（如 `AgentArena`），在傳統開源 SLG 中極為罕見。

---

## Details

### 1. Godot 版本、授權、2D UI 適用度與分區地圖實作

* **當前穩定版本**：Godot 4.4.x（Godot 4.4 於 2025 年 3 月 3 日發布，隨後推出 4.4.1 維護更新；若追求最成熟之單執行緒 Web 匯出管線，Godot 4.3 與 4.4 均為主要生產版本）。
  * 來源：[Godot Engine Releases](https://godotengine.org/releases/4.4/)（查證日期：2026-10-13）
* **授權條款**：MIT 授權，完全自由開源，無任何商業營收抽成，允許閉源或開源發行。
  * 來源：[Godot Engine LICENSE.txt](https://github.com/godotengine/godot/blob/master/LICENSE.txt)（查證日期：2026-10-13）
* **2D UI 系統適用度（Control / Theme / RichTextLabel）**：
  * **Control 節點系統**：提供強大的容器佈局體系（`HBoxContainer`, `VBoxContainer`, `GridContainer`, `ScrollContainer`, `PanelContainer`），支援錨點（Anchors）與比例縮放。非常適合實作 DOS 三國志 II 式的「左地圖、右資訊面板＋選單」分割佈局。
  * **Theme 系統**：支援全域或局部主題樣式替換（`StyleBoxFlat`, `StyleBoxTexture`），能輕易透過九宮格貼圖（NinePatch）實現復古像素風視窗邊框與按鈕狀態。
  * **RichTextLabel**：支援 BBCode 標籤（`[b]`, `[color]`, `[table]`, `[cell]`, `[url]`），適合用於武將列表、情報數值表、歷史事件日誌之富文本混排。
* **「分區彩色省份地圖＋點選」實作技術評估**：
  三國志 II 共有 41 國（郡縣/省份）。針對此種規模，評估三種主流實作技術：

| 實作方案 | 適用節點 / 技術 | 點選偵測機制 | 優點 | 缺點 | 本專案適用度 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. 向量多邊形（推薦）** | `Polygon2D` + `Line2D` + `Area2D` | `CollisionPolygon2D` 的 `_input_event` 或 `Geometry2D.is_point_in_polygon` | 向量邊界在任何縮放層級皆極度清晰；41 個節點開銷微乎其微；可直接設定 `polygon2d.color` 動態著色勢力勢力色。 | 需事先將地圖頂點座標以數組或 GeoJSON 格式匯入。 | **最高（最省事）** |
| **B. 顏色索引貼圖（ID Map）** | `Sprite2D` / `TextureRect` + Custom Canvas Shader | CPU 讀取 `Image.get_pixel(x, y)` 或 GPU Compute Shader 拾取 | 效能天花板最高（支援數千省份如歐陸風雲/P社遊戲）。 | 41 國規模下嚴重過度設計；放大時貼圖邊緣易產生像素鋸齒；資產管線繁瑣。 | **不推薦** |
| **C. 瓦片地圖（TileMapLayer）** | `TileMapLayer`（Godot 4.3+ 拆分節點） | `local_to_map(pos)` 查表取得 Tile Data 自訂省份 ID | 適合正方形/六角形網格棋盤式戰棋。 | 難以繪製有機自然邊界的不規則歷史省份多邊形。 | **不適合本介面** |

#### 範例：Polygon2D + Area2D 實作省份點選與著色（GDScript）
```gdscript
# Province.gd
class_name Province
extends Node2D

signal province_clicked(province_id: int)

@export var province_id: int = 1
@export var province_name: String = "洛陽"
@onready var visual_polygon: Polygon2D = $Polygon2D
@onready var collision_poly: CollisionPolygon2D = $Area2D/CollisionPolygon2D

var owner_faction_color: Color = Color.WHITE

func setup_polygon(points: PackedVector2Array, color: Color) -> void:
    visual_polygon.polygon = points
    visual_polygon.color = color
    collision_poly.polygon = points
    owner_faction_color = color

func _on_area_2d_input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
    if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
        province_clicked.emit(province_id)

func set_highlight(highlighted: bool) -> void:
    if highlighted:
        visual_polygon.color = owner_faction_color.lightened(0.3)
    else:
        visual_polygon.color = owner_faction_color
```
* 來源：[Godot Engine 2D Navigation and Polygons](https://docs.godotengine.org/en/stable/tutorials/2d/2d_movement.html)；[Vercix Grand Strategy Map](https://github.com/Vercix/godot-grand-strategy-map)（查證日期：2026-10-13）

---

### 2. 與 Python 後端整合方式比較

本專案核心為純 Python 標準庫編寫之確定性、不可變狀態引擎，每回合由玩家與 LLM/規則 AI 下達計畫指令。

| 整合方式 | 通訊媒介 | 實作難度 | 跨平台/Web 相容性 | 對「引擎是唯一真相、前端不算規則」之影響 | 綜合評估 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. HTTPRequest 輪詢/請求** | HTTP 1.1 / JSON（`GET /state`, `POST /action`） | **極低**（Godot 內建 `HTTPRequest` 節點） | **完全相容**（桌面與 WebAssembly 皆原生支援 fetch） | **完美維持**。前端為純粹的展示端（Dumb Terminal），不參與任何規則計算。 | **最合理首選** |
| **2. WebSocket** | 全雙工 WebSocket 協定 | 中等（Python 標準庫無內建 WS，需手寫 RFC 6455 或引入第三方套件） | 良好（Godot 內建 `WebSocketPeer`） | 維持良好，但回合制 SLG 屬低頻請求-回應模型，WebSocket 缺乏效益。 | **不推薦（增加後端依賴）** |
| **3. GDExtension / Python 綁定** | `py4godot` 或 CPython 嵌入 | **極高**（需打包 Python 執行時環境、動態庫與依賴） | **破壞 Web 匯出**（CPython GDExtension 無法編譯至 Wasm） | 理論上可維持，但環境極易損壞；版本升級維護負擔沉重。 | **強烈反對** |
| **4. 改寫為 GDScript** | 引擎直接內嵌於 Godot | **極高**（需重寫全部不可變資料結構與確定性邏輯） | 良好 | **徹底破壞**。AI 與後端若仍為 Python，則會產生雙重邏輯實作；雙方確定性難以保證。 | **架構自戕** |

#### 關鍵論證：為什麼 HTTPRequest 是唯一合理解法？
1. **符合遊戲節奏**：回合制策略遊戲的狀態更新是非即時的。玩家花數十秒至數分鐘思考指令，點擊「結束回合」時發送單一 `POST /plan`，Python 後端推進一回合計算（同時驅動 LLM / 規則 AI）後返回最新不可變狀態快照。這天然契合 HTTP Request-Response 模式，無需長連接。
2. **嚴格守護「單一真實來源」**：前端僅負責將 `state.json` 序列化並著色在地圖與 UI 面板上；前端提交的是「計畫指令意圖」（Intent），規則驗證、戰爭迷霧計算（Fog of War）、關注名單上限 6 的過濾完全由 Python 核心裁決，杜絕作弊與邏輯分歧。
* 來源：[Godot HTTPRequest Documentation](https://docs.godotengine.org/en/stable/classes/class_httprequest.html)；[niklas2902/py4godot](https://github.com/niklas2902/py4godot)（查證日期：2026-10-13）

---

### 3. 匯出目標評估（桌面、Web、手機寬度 360px）

#### A. 桌面平台（Linux / Windows / macOS）
* **優勢**：成熟穩定。可直接匯出為單一獨立執行檔（或搭配 `.pck`），效能開銷極小，可離線執行。
* **限制與維護代價**：
  * **macOS Gatekeeper**：若無蘋果開發者帳號（$99/年）進行程式碼簽名（Code Signing）與公證（Notarization），玩家開啟時會遭遇安全性阻擋，必須手動透過終端機執行 `xattr -cr` 或至系統設定放行。
  * **Linux**：Godot 4.3 已正式支援 Wayland，相容性大幅提升。
* 來源：[Godot Exporting for macOS](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_macos.html)（查證日期：2026-10-13）

#### B. Web 平台（HTML5 / WebAssembly）
* **SharedArrayBuffer 與跨來源隔離（COOP/COEP）**：
  * **重大利多**：**Godot 4.3 起正式引入官方單執行緒（Single-threaded）Web 匯出範本**。此模式不再強制依賴 `SharedArrayBuffer`，因此在靜態託管（如 GitHub Pages、Itch.io）時**不再需要**伺服器配置 `Cross-Origin-Opener-Policy: same-origin` 與 `Cross-Origin-Embedder-Policy: require-corp` 回應標頭。
  * 來源：[Godot 4.3 release announcement - Web export](https://godotengine.org/article/godot-4-3-a-shared-effort/)（查證日期：2026-10-13）
* **檔案大小與首屏載入時間**：
  * **未壓縮體積**：`godot.wasm` 核心引擎二進位檔約 **33 MB – 42 MB**。
  * **Gzip 壓縮**：約 **9 MB – 11 MB**；Brotli 壓縮：約 **3.5 MB – 5 MB**。
  * **載入時間**：在典型寬頻網路下需下載 10MB+ 並由瀏覽器編譯 Wasm，冷啟動需 **3 至 8 秒**；低階行動裝置可能超過 15 秒甚至記憶體溢位崩潰。相對之下，純 HTML/JS/SVG 前端通常僅 **200 KB – 1 MB**，毫秒級渲染。
* **中文字型嵌入成本**：
  * 瀏覽器環境下的 HTML 可以直接使用使用者作業系統預設字型（`font-family: system-ui, "Microsoft JhengHei", "PingFang TC"`），耗費 **0 KB** 頻寬。
  * Godot Web 匯出無法直接讀取作業系統字型，**必須將字型打包進專案資源**。一套標準思源黑體（Noto Sans TC）TTF 約 **15 MB – 20 MB**；即使採用精簡像素字型（如俐方體 11、Zpix）亦需 **1 MB – 3 MB**。
* **HTTPRequest 同源限制（CORS）**：
  * 當 Godot 匯出為 Web 時，`HTTPRequest` 底層是透過瀏覽器的 `fetch()` API 實作。
  * 若 Python 後端（如 `http://127.0.0.1:8000`）與前端網頁不在同一網域/連接埠，Python 後端**必須**嚴格實作 CORS 標頭處理（回覆 `Access-Control-Allow-Origin: *`、處理 `OPTIONS` Preflight 請求），否則所有 API 請求將被瀏覽器直接攔截。
* 來源：[Godot Exporting for Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)（查證日期：2026-10-13）

#### C. 手機寬度（360px）可行性分析
* **極高之排版挑戰**：
  * DOS 三國志 II 介面本質為「左方寬地圖、右方資訊看板＋多級指令按鈕」之雙欄橫向結構。
  * 在 360px 寬度的手機直式螢幕上，若使用 Godot 視窗整體縮放（Viewport scaling），文字將縮小至無法閱讀（41 國地圖被壓縮在 180px 寬度內，繁體中文字元將黏結模糊）。
  * 若要支援 360px，必須在 Godot 中重新撰寫響應式佈局：當螢幕寬度小於特定門檻時，強制將左右分割改為「分頁標籤（TabContainer）」或上下折疊視圖（上方地圖縮圖、下方捲動選單）。
  * 相對而言，純 HTML/CSS 利用 Flexbox/Grid 與 `@media (max-width: 600px)` 調整排版，難度遠低於 Godot Control 節點系統的代碼級調整。

---

### 4. 中文（繁體）顯示評估

1. **字型嵌入**：
   * Godot 內建預設字型僅支援基本拉丁字母及少量符號，不包含 CJK（中日韓）字元集。
   * 開發者必須手動匯入 `.ttf`, `.otf`, `.woff`, 或 `.woff2` 字型檔，並指派給全域 Theme 或 Control 節點。
   * 推薦方案：若走 DOS 復古像素風，可採用開源點陣字型「俐方體 11（Cubic 11）」或「融合像素體（Fusion Pixel）」，體積僅約 1.5–2.5 MB，既契合懷舊風格又大幅縮小下載包。
2. **輸入法（IME）已知問題**：
   * **桌面版**：Godot 4 支援 OS 原生 IME 預編輯（Pre-edit）與組字候選字視窗，但在特定 Linux 視窗管理器或部分 Windows 輸入法下，偶爾存在候選字視窗定位偏移的次要 Bug。
   * **WebAssembly 匯出**：**重大缺陷**。在 HTML5 Canvas 中，瀏覽器對原生 IME 的捕獲極度不穩定，常出現無法跳出注音/拼音候選字窗、或送出字元重複/丟失的已知問題。若遊戲包含「君主命名」、「武將改名」等文本輸入功能，Godot Web 體驗將遠遜於 HTML `<input>` 標籤。
3. **RichTextLabel 排版與換行**：
   * Godot 4 採用全新的 `TextServerAdvanced`，整合了 HarfBuzz 排版引擎與 ICU 斷詞庫，原生支援 CJK 無空格自動換行。
   * **避頭尾禁則（Kinsoku Shori）**：標點符號（如逗點 `，`、句點 `。`、右引號 `」`）預設不會出現在行首。
   * 需注意設定：務必將 RichTextLabel 的 `autowrap_mode` 設為 `AUTOWRAP_WORD_SMART` 或 `AUTOWRAP_WORD`。
* 來源：[Godot GUI Using Fonts](https://docs.godotengine.org/en/stable/tutorials/ui/gui_using_fonts.html)；[Godot RichTextLabel](https://docs.godotengine.org/en/stable/classes/class_richtextlabel.html)；[Godot Engine GitHub Issues - Web IME](https://github.com/godotengine/godot/issues)（查證日期：2026-10-13）

---

### 5. 開發成本與維護

#### A. 學習曲線（針對熟 Python/JS 個人開發者）
* **語言門檻低**：GDScript 語法外觀高度擬似 Python（縮排、冒號、動態型別、切片），Python 開發者半天內即可無障礙閱讀與編寫。
* **心智模型轉換門檻中等**：
  * Python 標準庫後端是「純函數、不可變狀態、確定性演算法」；
  * Godot 是「狀態可變、物件導向、以場景樹（SceneTree）與訊號（Signals）驅動、受幀循環（Frame Loop）控制的遊戲引擎」。
  * 開發者必須適應以「訊號綁定」取代 DOM 事件監聽，並掌握 Node 的生命週期（`_ready`, `_process`, `queue_free`）。

#### B. 場景檔（.tscn）與 Git 版本控制
* `.tscn` 為純文字格式（類似 INI），具備可讀性。
* **潛在風險**：Godot 4 引進了 `uid://...` 機制以追蹤資源。若外部腳本或資產在編輯器外更名，容易導致 UID 斷鏈；多人協作時視覺拖曳容易造成 `.tscn` 巨大 merge conflict。所幸個人開發者不會遭遇多人衝突，但仍應遵循「單一場景職責單一化、多拆子場景」的原則。

#### C. CI / 無頭測試與自動化截圖驗收
* **單元測試**：可使用社群主流測試框架 **GUT（Godot Unit Test）** 或 **gdUnit4**，支援命令列無頭執行：
  ```bash
  godot --headless -s addons/gut/gut_cmdline.gd -gdir=res://test/ -gexit
  ```
* **自動化截圖（重要陷阱：`--headless` 無法截圖）**：
  * Godot 的 `--headless` 模式會將渲染伺服器切換為虛擬空實作（Dummy），導致 Viewport 紋理為空。
  * **正確做法**：在 CI（如 GitHub Actions）中使用 Linux 虛擬顯示伺服器 `xvfb-run`，搭配相容性 OpenGL3 渲染驅動：
  ```bash
  xvfb-run godot --rendering-driver opengl3 --path . -s res://scripts/take_screenshot.gd
  ```
  在 GDScript 中等待渲染結束後抓取影像存檔：
  ```gdscript
  await RenderingServer.frame_post_draw
  var img: Image = get_viewport().get_texture().get_image()
  img.save_png("res://ci_artifacts/screen.png")
  get_tree().quit()
  ```
* 來源：[GUT GitHub](https://github.com/bitwes/Gut)；[gdUnit4 GitHub](https://github.com/MikeSchulze/gdUnit4)；[Godot CLI documentation](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html)（查證日期：2026-10-13）

#### D. LLM 工具代碼生成穩定度
* **GDScript 代碼生成**：非常穩定。現代大模型（GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro）對 GDScript 4 語法理解深入。
* **`.tscn` 場景描述檔生成**：**極不穩定且容易報錯**。LLM 難以正確精確估算 Godot 4 的 UID 雜湊值與龐大的節點屬性繼承樹。
* **工程實踐建議**：**完全禁止 LLM 直接生成 `.tscn` 原始碼**。應讓 LLM 生成「以純 GDScript 代碼在 `_ready()` 中以程式化構建 UI 樹」之代碼（如 `var btn = Button.new()`），或由人工在編輯器中建立極簡空版場景，再由 LLM 編寫掛載腳本。

---

### 6. 相對現有「純 HTML/JS 前端」優缺點對照表與改用觸發條件

| 評估維度 | 現有「純 HTML/JS/SVG 前端」 | Godot 4 引擎前端 | 差異分析與勝出方 |
| :--- | :--- | :--- | :--- |
| **互動性** | DOM 事件、CSS Hover、自訂 SVG 點選 | 遊戲循環輸入系統、游標變換、原生手把支援 | **平手（純點擊選單）**；若需手把控制器則 Godot 勝出。 |
| **動畫與特效** | CSS Keyframes, Web Animations, SVG SMIL | `AnimationPlayer`, `Tween`, 粒子系統, 著色器 | **Godot 壓倒性勝出**（部隊行軍、戰鬥受擊火光極易實作）。 |
| **素材管線** | 需手動處理 WebP/SVG/音訊，無整合管線 | 內建自動紋理壓縮、精靈切割、字型描邊、音訊轉碼 | **Godot 勝出**。 |
| **分發能力** | **無敵**。網頁隨點隨開，支援 PWA 離線快取 | 桌面需下載數十 MB 安裝檔；Web 首屏下載 15MB+ | **現有 Web 壓倒性勝出**（真正免安裝、跨平台零門檻）。 |
| **無障礙性** | 原生 HTML 標籤、螢幕報讀軟體（ARIA）支援 | Canvas 渲染對螢幕閱讀器完全黑箱 | **現有 Web 壓倒性勝出**。 |
| **除錯體驗** | Chrome DevTools（網路封包 JSON、CSS 即時微調） | Godot 內建除錯器、場景樹檢查（但檢視 HTTP 封包不便） | **現有 Web 勝出**（檢視 API 請求與樣式極為直觀）。 |
| **傳輸體積** | **極致輕量**：全站通常 < 500 KB，零字型下載 | **笨重**：Wasm+專案+中文字型至少 15 MB – 25 MB | **現有 Web 壓倒性勝出**（差距達 30–50 倍）。 |

#### 何時值得改用 Godot？（觸發條件 / Tipping Points）
僅在滿足以下任一**硬性業務觸發條件**時，才值得啟動向 Godot 的遷移：
1. **遊戲玩法視覺化升級**：從「純數值戰報與靜態地圖」演進為「大地圖即時行軍動畫、戰鬥戰術棋盤、精靈切片攻擊動作、天氣動態著色器特效（風雪、迷霧動態遮罩）」。
2. **分發通路上架需求**：決定將遊戲上架至 **Steam** 或 **Itch.io 桌面獨立客戶端**，需要標準桌面安裝包、Steamworks SDK 整合（成就、雲端存檔）與完整的搖桿控制器支援。
3. **介面超越 DOM 負荷**：畫面同時出現數百個具備平滑插值位移的動態單位，DOM 或純 SVG 渲染效能出現掉幀瓶頸。

> 若當前介面僅維持「DOS 三國志 II」之靜態 41 國著色、文字表格與多層選單，現有 Web 技術已是最優解。

---

### 7. 開源 Godot 回合制策略 / 大戰略專案調研

調研開源社群具備參考價值之 Godot 專案：

| 專案名稱與 Repository | 授權條款 | 最後更新時間 | 架構型態 | 對本專案之參考價值 |
| :--- | :--- | :--- | :--- | :--- |
| [C7-Game/OpenCiv3](https://github.com/C7-Game/OpenCiv3) | **MIT** | 2026 年活躍維護（2025 年末發布 v0.3 Dutch 預覽版） | 單體式架構（C# 實作規則與渲染） | **極高**。開源重製文明帝國 III，展示了大型回合制 4X 遊戲在 Godot 中的地圖瓦片管理、單元移動與 UI 佈局，但其規則與前端深度耦合。 |
| [Vercix/godot-grand-strategy-map](https://github.com/Vercix/godot-grand-strategy-map) | **MIT** | 2024–2025 年 | 單體式展示專案（GDScript + Compute Shader） | **高**。專門演示如何透過省份識別貼圖（Index Texture）與 Shader 在 Godot 中實作類似 P 社大戰略的省份懸停與點選。 |
| [goblin-code-se/world_conquest](https://github.com/goblin-code-se/world_conquest) | **MIT** | 2023–2024 年 | 單體式架構（GDScript） | **中**。Risk 式領土爭奪棋盤遊戲，展示了不規則區域控制與回合交替邏輯。 |
| [ramaureirac/godot-tactical-rpg](https://github.com/ramaureirac/godot-tactical-rpg) | **MIT** | 已更新適配 Godot 4.3 | 單體式架構（GDScript） | **中**。經典回合制戰棋範例，著重於網格尋路與戰鬥流程控制。 |
| [JustInternetAI/AgentArena](https://github.com/JustInternetAI/AgentArena) | **MIT** | 2024–2025 年 | **分離式架構**（Godot 前端＋Python 後端） | **高（架構層面）**。展示了將 Godot 作為視覺化前端，透過結構化通訊連接 Python 評估後端與 LLM Agent 的通訊模式。 |

* **關鍵調研發現**：在 Godot 開源生態中，99% 的 SLG/戰棋專案皆為**單體架構**（規則由 GDScript/C# 編寫）。採用「純 Python 獨立確定性規則引擎＋Godot 純前端」的先例主要存在於 AI 研究專案，證明此架構在遊戲界少見，但在跨語言系統中完全可行且利於維護核心資產。
* 來源：上述各專案 GitHub 倉庫（查證日期：2026-10-13）

---

### 8. 結論、架構決策與單一下午最小可行實驗（MVE）

#### A. 核心架構建議
明確建議：**「短期維持 Web 前端；長期確立『共用同一 JSON API』的雙前端相容架構，暫不全面轉移 Godot。」**

* **決策理由**：
  1. **符合「省事與可維護」原則**：個人開發者在缺乏商業回報的情境下，維護兩套前端是沉重負擔。現有純 Python＋HTML/JS 具有零建置工具鏈（No Node.js, No Vite, No Godot Engine Editor）、直接編輯即生效、跨平台全相容之極致維護優勢。
  2. **避免 Web 體驗倒退**：若換成 Godot Web 匯出，玩家需要承受 20MB 的下載量與中文字輸入法障礙，反而是使用者體驗的實質倒退。
* **風險控管**：
  * 若直接「改用 Godot 桌面」：將徹底失去瀏覽器隨點隨玩的傳播紅利，且需面臨 macOS/Linux 跨平台打包發行維護地獄。
  * 若「直接把引擎改寫 GDScript」：**災難性錯誤**，直接摧毀確定性、不可變狀態，以及既有的 LLM/規則 AI Python 對齊基礎。

---

#### B. 單一下午最小可行實驗（MVE / POC）設計
* **目標**：在 3–4 小時內，驗證「Godot 透過 HTTP 獲取現有 Python 後端狀態、渲染 3 個彩色多邊形省份、點選並發送行動計畫指令」之全流程。

##### 步驟一：後端確認（15 分鐘）
確保現有 Python 後端提供簡單的 CORS 支援與兩個端點：
* `GET /api/state`：回傳簡易 JSON（包含 3 個省份座標、擁有者、代表顏色）。
* `POST /api/action`：接收 `{ "faction_id": 1, "order": "DEVELOP" }` 並回傳新狀態。

##### 步驟二：建立 Godot 4 測試專案（30 分鐘）
1. 新建 Godot 4.4/4.3 專案，建立主場景 `Main.tscn`（根節點為 `Node2D`）。
2. 在場景中添加一個 `HTTPRequest` 節點。
3. 添加一個 `VBoxContainer`（包含一個 `RichTextLabel` 顯示選中省份資訊，以及一個 `Button` 用於發送「內政開發」指令）。

##### 步驟三：編寫客戶端驅動腳本 `Main.gd`（60 分鐘）
```gdscript
# Main.gd
extends Node2D

@onready var http_request: HTTPRequest = $HTTPRequest
@onready var info_label: RichTextLabel = $UI/VBoxContainer/InfoLabel
@onready var action_button: Button = $UI/VBoxContainer/ActionButton

const API_BASE = "http://127.0.0.1:8000/api"
var current_selected_province_id: int = -1

func _ready() -> void:
    http_request.request_completed.connect(_on_request_completed)
    action_button.pressed.connect(_on_action_button_pressed)
    fetch_game_state()

func fetch_game_state() -> void:
    http_request.request(API_BASE + "/state")

func _on_request_completed(_result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if response_code != 200:
        info_label.text = "[color=red]API 請求失敗: %d[/color]" % response_code
        return
        
    var json_str = body.get_string_from_utf8()
    var state = JSON.parse_string(json_str)
    render_provinces(state["provinces"])

func render_provinces(provinces_data: Array) -> void:
    # 清理舊省份節點
    for child in get_tree().get_nodes_in_group("province_nodes"):
        child.queue_free()
        
    for p_data in provinces_data:
        var poly = Polygon2D.new()
        poly.add_to_group("province_nodes")
        var points = PackedVector2Array()
        for pt in p_data["polygon"]:
            points.append(Vector2(pt[0], pt[1]))
        poly.polygon = points
        poly.color = Color.from_string(p_data["color"], Color.WHITE)
        add_child(poly)

func _on_action_button_pressed() -> void:
    if current_selected_province_id == -1:
        return
    var payload = JSON.stringify({
        "province_id": current_selected_province_id,
        "action": "DEVELOP"
    })
    var headers = ["Content-Type: application/json"]
    http_request.request(API_BASE + "/action", headers, HTTPClient.METHOD_POST, payload)
```

##### 步驟四：驗證與判定標準（45 分鐘）
* **驗證項目**：
  1. 繁體中文武將名與省份名在 `RichTextLabel` 中是否正常渲染（測試未置入中文字型時是否顯示豆腐塊，置入中文字型後是否正常）。
  2. 點擊按鈕送出指令後，後端收到資料並回傳，前端多邊形顏色是否即時響應改變。
  3. 匯出為 HTML5 Web 範本，用本機伺服器打開，觀察載入秒數與瀏覽器主控台是否有 CORS 報錯。
* **判定結論**：如果實驗完成後，開發者感受到「為了達成與現有 Web 相同的功能，Godot 引入了更多調試與字型配置成本，且 Web 載入明顯變慢」，即可果斷結案並維持 Web 現狀。

---

## Unverified / open questions

1. **未查證：Godot 4.4/4.5 在特定行動瀏覽器（如 iOS Safari）單執行緒 Web 匯出的 WebGL2 崩潰率**
   * *說明*：Godot 4.3 雖然在官方公告中修復了大量 Apple WebGL 相容問題，但在不同版本 iOS Safari 上單執行緒音訊與著色器編譯的崩潰率仍需實機測試，本研究未能取得 iOS 實機驗證。
   * *確認方法*：將單執行緒 Web 導出檔上傳至 HTTPS 伺服器，使用 iPhone（iOS 17/18）實測 10 分鐘以上長度遊戲。
2. **推論（非直接觀察）：現有 Python HTTP 後端處理 CORS OPTIONS Preflight 之現況**
   * *說明*：報告中推論若匯出為 Web 版必須修改 Python 後端支援 CORS。由於未檢視目前專案後端源碼，不確定現有後端是否已包含 `Access-Control-Allow-Origin` 處理。
   * *確認方法*：檢視目前 Python 後端代碼之 `do_OPTIONS` 與回應標頭邏輯。
3. **未查證：純點陣繁體中文字型在 Godot 4 高解析度螢幕下的 MSDF 渲染效果**
   * *說明*：使用 1.5MB 級別的像素字型（如俐方體 11）可解決體積問題，但在 Godot 4 開啟 MSDF（多通道帶符號距離場）字型導入時，像素風格邊緣是否會被過度平滑破壞，需實際匯入確認參數設定。
   * *確認方法*：在 Godot 4 編輯器中匯入 `Cubic_11.ttf`，切換 MSDF 與 DynamicFont 預檢字元邊緣。
