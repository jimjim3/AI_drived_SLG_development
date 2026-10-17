# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)

## 評測設定
- **評測席位 (Seat)**: `faction_2`
- **情境 (Scenario)**: `default`
- **評測種子數**: 計畫種子 6 個，實際完成 6 個 (種子: `[0, 1, 2, 3, 4, 5]`)
- **呼叫預算 (Max Calls)**: 130
- **已使用呼叫數 (Calls Used)**: 125 (未觸發提前終止)

## 評測摘要

| 指標 | 數值 |
| --- | --- |
| 評測席位 (seat) | faction_2 |
| 基準線勝率 (baseline_win_rate) | 0.0% |
| 實驗組勝率 (experiment_win_rate) | 33.3% |
| 勝率差異 (win_rate_delta) | +33.3% |
| 平均城池差 (mean_cities_delta) | -0.17 |
| 平均兵力差 (mean_troops_delta) | -1050.3 |
| 指令接受率 (orders_accept_rate) | 76.8% |
| 計劃失敗率 (plan_failure_rate) | 0.8% |
| 每回合委任數 (delegated_per_turn) | 9.43 |
| LLM 呼叫次數 (calls) | 125 |
| 估計 Token 數 (est_tokens) | 313653 |
| 解析失敗次數 (parse_failures) | 2 |
| 呼叫錯誤次數 (errors) | 4 |

**可能原因提示**：指令被拒比例偏高，主因：action 'recruit' not legal

## 逐種子明細

| 種子 | 基準勝者 | 基準城數/兵力 | 實驗勝者 | 實驗城數/兵力 | 城池差 | 兵力差 | 呼叫數 | 成功/被拒/委任 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | faction_1 | 3 城 / 10000 兵 | faction_1 | 3 城 / 7530 兵 | +0 | -2470 | 21 | 92 / 28 / 188 |
| 1 | faction_1 | 3 城 / 9800 兵 | faction_2 | 3 城 / 11300 兵 | +0 | +1500 | 20 | 85 / 35 / 195 |
| 2 | faction_1 | 3 城 / 9700 兵 | faction_1 | 2 城 / 4400 兵 | -1 | -5300 | 20 | 90 / 32 / 190 |
| 3 | faction_1 | 3 城 / 10000 兵 | faction_1 | 3 城 / 9902 兵 | +0 | -98 | 22 | 86 / 27 / 194 |
| 4 | faction_1 | 3 城 / 10000 兵 | faction_2 | 3 城 / 8566 兵 | +0 | -1434 | 21 | 98 / 22 / 182 |
| 5 | faction_1 | 3 城 / 9900 兵 | 無 | 3 城 / 11400 兵 | +0 | +1500 | 21 | 98 / 22 / 182 |

## 診斷

### 動作分布 (基準線 vs 實驗組)

| 動作 | 基準線次數 | 實驗組次數 | 差異 |
| --- | --- | --- | --- |
| develop_agri | 366 | 332 | -34 |
| develop_commerce | 69 | 136 | +67 |
| develop_defense | 281 | 335 | +54 |
| move | 0 | 72 | +72 |
| recruit | 236 | 223 | -13 |
| rest | 728 | 578 | -150 |
| siege | 0 | 4 | +4 |

### 攻城勝敗 (出征 / siege_outcomes)

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 攻城嘗試 (siege attempts) | 0 | 4 | +4 |
| 成功攻克 (captured) | 0 | 0 | +0 |
| 擊退受挫 (repelled) | 0 | 4 | +4 |

### 出奔 / 抗旨 / 武將流失

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 出奔數 | 0 | 0 | +0 |
| 抗旨數 | 0 | 0 | +0 |
| 初始武將數 | 14 | 14 | +0 |
| 最終存活武將數 | 14.0 | 14.0 | +0.0 |
| 武將流失數 | 0.0 | 0.0 | +0.0 |
| 最終平均忠誠 | 88.7 | 80.8 | -7.9 |

### 被拒指令原因前 3 名

| 排名 | 原因 | 次數 |
| --- | --- | --- |
| 1 | `action 'recruit' not legal` | 76 |
| 2 | `param troops=N out of range [N, N]` | 24 |
| 3 | `action 'develop_commerce' not legal` | 20 |

### 點名與委任平均 (每回合)

| 類別 | 平均人數 |
| --- | --- |
| 點名執行 (Orders) | 4.58 |
| 系統委任 (Delegated) | 9.43 |

## 預算保護
- **max_calls**: 130
- **calls_used**: 125
- **stopped_early**: 否 (False)

## 錯誤樣本

1. `Request failed: TimeoutError: The read operation timed out`
2. `parse: JSON 語法錯誤：Unterminated string starting at: line 88 column 16 (char 1798)`
3. `parse: JSON 語法錯誤：Expecting value: line 89 column 118 (char 2011)`

## 限制說明與注意事項
> [!NOTE]
> **同座位比較、樣本數小時差異不具統計顯著性**。
>
> 1. **同座位比較之必要性**：各勢力在初始地緣、將領與兵力配置上存在結構性差異（例如 faction_1 曹操勢力結構上較強），不可直接比較各勢力勝率，必須比較同座位、同種子下 LLM 與規則 AI 的差異。
> 2. **統計顯著性**：SLG 模擬包含隨機事件與連鎖決策效應，當評測種子數量較少時，指標差異易受單局偶發狀況影響，不具統計顯著性。建議以較多種子（例如 20 個以上）進行正式評估。
