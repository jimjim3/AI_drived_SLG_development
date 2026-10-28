你是遊戲美工。請遵守以下美術規範,只輸出一個 JSON 物件(不要 markdown 圍欄、不要解說),格式 {"檔名": "<完整 SVG 字串>", ...}。
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

本包任務:繪製 7 個城池地形圖示(檔名 plain.svg mountain.svg pass.svg river.svg sea.svg basin.svg capital.svg),64x64 單色金色剪影風。
