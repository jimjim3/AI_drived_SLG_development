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
改用 agy 的 `generate_image` 出水墨膠彩插畫,取代色塊式 SVG。已接入:9 座城池橫幅、四個圓形徽章(圓形遮罩 PNG)、三個結局畫面(勝利/敗北/平手)、野戰與叛逃場景。第一次因 agy 圖像後端 429 配額用完只畫出 10 張,隔日重送後補齊 8 張。主選單背景 `menu.png` 已畫好但尚未接入(標題畫面沿用原圖)。其餘季節與事件場景仍為 SVG,舊 SVG 保留作為載入失敗時的備援。圖像提示詞須要求「滿版、無邊框、無文字」,避免米色紙邊與假字。原圖 PNG(約 2 MB/張)不入庫,網頁用壓縮版(JPEG 約 0.1–0.2 MB)。
