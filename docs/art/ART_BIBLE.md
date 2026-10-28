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
- 打回重做(存放 `art_work/rework/`,未上線):spring autumn(畫面過空)、siege(構圖雜亂)、famine(元素不清)。
- 已接線:僅 favicon。徽記/圖示/插圖尚未接進 UI(下一步)。
- 戰區圖改由 `scripts/build_theatre_maps.py` 依真實經緯度(agy 回報,未核對)程式繪製。
