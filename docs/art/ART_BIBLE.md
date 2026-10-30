# 美術規範(總編輯 Claude 制定,美工 agy 執行)
- 風格:深色古風戰略遊戲 UI;背景 #0b1220/#0f1724,金色強調 #fbbf24,米色文字 #e8d9b0。線條簡潔、單色或雙色剪影,不用漸層照片感。
- 陣營色(與現有 UI 一致):魏 faction_1 藍 #3b82f6、蜀 faction_2 綠 #10b981、吳 faction_3 紅 #ef4444、迷霧/中立 灰 #64748b。
- 格式:純 SVG,不引用外部圖片/字型,每個檔案自帶 viewBox,無 <script>。圖示 viewBox 0 0 64 64;插圖 0 0 640 360。
- 文字:SVG 內若有字只用繁體中文。
- 驗收(總編輯逐張看渲染圖):可辨識、符合配色、小尺寸(32px)仍清楚、無亂碼/截斷、與史實或遊戲設定不衝突。
## 交付包
1. emblems:faction_1/2/3 徽記 + neutral
2. icons_city:城池地形圖示 plain(平原) mountain(山地) pass(關隘) river(臨江) sea(臨海) basin(盆地) capital(都城)
3. icons_action:行動圖示 develop recruit march siege scout defend report end_turn
4. scenes:季節插圖 spring summer autumn winter,事件插圖 siege battle defection famine
5. favicon:遊戲圖示

## 驗收紀錄(2026-10-29,總編輯目測渲染圖)
- 通過並已放入 `web/static/assets/art/`:emblems×4、icons×15(城池 7 + 行動 8)、favicon、scenes: summer winter battle defection。
- 打回的 4 張(spring autumn siege famine)已由 agy 重做,第二版通過並上線 `assets/art/scenes/`。
- 已接線:favicon、地圖節點徽記、派遣面板行動圖示、回合報告的季節橫幅(`scene.key`)。尚未接線:城池地形圖示、battle/defection/siege/famine 事件插圖、行動圖示僅用在派遣面板。
- 戰區圖改由 `scripts/build_theatre_maps.py` 依真實經緯度(agy 回報,未核對)程式繪製。

## 遊戲 9 城座標 vs 真實地理(2026-10-29,以 agy 回報經緯度、各自正規化到 0–1 比較)
大方向正確(西→東、北→南),屬風格化配置;偏差較大者(遊戲座標 − 真實):漢中 y −0.36(真實與宛、洛陽緯度相近,遊戲畫得太南)、許昌 y −0.23、襄陽 y −0.20、宛 y −0.16、許昌 x +0.16。其餘(洛陽、陳留、建業、吳郡、會稽)偏差 ≤ 0.13。
**未修改**:座標與相鄰關係是已評測平衡(含孫權東南角優勢)的一部分,改動會使既有評測失效;如要「貼近真實」,應列為新的地圖變體再重測。
- 另已接線:城池地形圖示(9 城各指定一種)、攻城/會戰/叛離事件插圖(`status.story_art`)。

## 第二輪(2026-10-29)
- 通過並上線:9 張城池風景 `assets/art/cities/`(漢中/洛陽/宛/許昌 第一版被打回——四張都像同一座塔——重做後通過)、結局 4 張 `assets/art/endings/`(victory defeat draw menu)、戰役插圖 2 張(chibi_fire guandu_raid,在 `scenes/`)。
- 已接線:城池情報面板的城池橫幅、結束畫面(勝/敗/平)。**尚未接線**:menu.svg(主選單背景)、chibi_fire/guandu_raid(目前沒有對應的遊戲事件)。
- 觀感備註:城池圖多為剪影風,辨識度中等;我只看了縮圖/面板內大小。

## 輪 3:agy 圖像生成(2026-10-29/30)
改用 agy 的 `generate_image` 出水墨膠彩插畫,取代色塊式 SVG。已接入:9 座城池橫幅、四個圓形徽章(圓形遮罩 PNG)、三個結局畫面(勝利/敗北/平手)、野戰與叛逃場景。第一次因 agy 圖像後端 429 配額用完只畫出 10 張,隔日重送後補齊 8 張。主選單背景已換成新圖(舊標題圖備份於 `art_work/title_banner_old.jpg`);春夏秋冬四季場景已換新。攻城、飢荒、赤壁火攻、官渡燒糧四張因配額再度用完未畫成,待重置後補畫;舊 SVG 保留作為備援。圖像提示詞須要求「滿版、無邊框、無文字」,避免米色紙邊與假字。原圖 PNG(約 2 MB/張)不入庫,網頁用壓縮版(JPEG 約 0.1–0.2 MB)。

## 輪 4:ComfyUI Qwen-Image 2.1(2026-10-30)
使用者提供的 Colab ComfyUI(伺服器連結會重設,不入庫)。可用工作流:UNETLoader `qwen_image_2.1_int8_convrot` + CLIPLoader `qwen3vl_8b_int8_convrot`(type qwen_image)+ `TextEncodeQwenImage21` + KSampler(25 步、cfg 1.0、euler/simple);每張約 40 秒。第一次用錯文字編碼器(prompt-enhancer 那個)與 cfg 4 出雜訊圖。
已接入:全部 48 張頭像(42 武將、3 君主、3 通用,256 px,舊版備份 `art_work/portraits_old/`)、攻城/飢荒/赤壁火攻/官渡燒糧場景、三勢力開局軍議圖(開局卡片頂端)、三勢力勝利/敗北結局(依玩家勢力,缺檔退回通用圖再退回 SVG)、金/糧圖示(上方狀態列)。
已畫好、已壓縮入庫但尚無觸發點:出兵/抵達/斥候/開發/築防/被俘/援軍/外交/夜營/徵兵/迷霧/等待結算場景(`scenes/`)、七個資源圖示(`icons/ui_*.png`)、三面大旗與三張君主大圖(`extra/`)。羊皮紙地圖為真實中國輪廓,與遊戲抽象座標對不上,未使用。
品質備註:提示詞要求「無文字」對旗幟無效時,改構圖(去掉旗幟)才有效;被拒圖存於 `art_work/img/extra_rejected/`。

### 輪 4 補充:大地圖與資料庫武將頭像(2026-10-30)
- **大地圖**:用同一個 ComfyUI 畫三版鳥瞰地形(北在上,黃河在上緣、秦嶺在西、長江橫貫下半、海在右側),疊上九城座標後選第一版為底圖(`assets/art/map_painted.jpg`,水平拉伸 8% 讓吳郡、會稽貼近海岸;屬粗略對位,非精確地理)。載入失敗退回舊 `map_terrain.svg`。
- **資料庫武將頭像**:`data/sanguo/` 186 位武將中遊戲未使用的 144 位,已用姓名、標籤、年齡層與簡介組成提示詞全部畫出,檔名即資料庫 id(`assets/portraits/<id>.png`,256 px)。僅看過總覽圖,未逐張放大檢查;同一模型下面孔偏相似,辨識主要靠冠帽、甲冑與勢力色。
