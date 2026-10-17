⚠️ 後端連續失敗，評測已中止：後端連續失敗（5 次）：Request failed: TimeoutError: The read operation timed out

# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)

## 評測設定
- **評測席位 (Seat)**: `faction_2`
- **情境 (Scenario)**: `advantage`
- **評測種子數**: 計畫種子 10 個，實際完成 1 個 (種子: `[0]`)
- **呼叫預算 (Max Calls)**: 300
- **已使用呼叫數 (Calls Used)**: 14 (已中止（後端連續失敗（5 次）：Request failed: TimeoutError: The read operation timed out）)

## 評測摘要（⚠️ 實驗組實為規則 AI 代打，結果無效）

> [!WARNING]
> 實驗組實為規則 AI 代打，結果無效（全部 LLM 呼叫皆失敗）。

| 指標 | 數值 |
| --- | --- |
| 評測席位 (seat) | faction_2 |
| 基準線勝率 (baseline_win_rate) | 100.0% |
| 實驗組勝率 (experiment_win_rate) | 100.0% |
| 勝率差異 (win_rate_delta) | +0.0% |
| 平均城池差 (mean_cities_delta) | +0.00 |
| 平均兵力差 (mean_troops_delta) | +337.0 |
| 指令接受率 (orders_accept_rate) | 87.5% |
| 計劃失敗率 (plan_failure_rate) | 80.0% |
| 每回合委任數 (delegated_per_turn) | 12.65 |
| LLM 呼叫次數 (calls) | 14 |
| 估計 Token 數 (est_tokens) | 77142 |
| 解析失敗次數 (parse_failures) | 0 |
| 呼叫錯誤次數 (errors) | 33 |

**可能原因提示**：有武將出奔，檢查冷落機制；指令被拒比例偏高，主因：action 'develop_commerce' not legal

## 逐種子明細

| 種子 | 基準勝者 | 基準城數/兵力 | 實驗勝者 | 實驗城數/兵力 | 城池差 | 兵力差 | 呼叫數 | 成功/被拒/委任 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | faction_2 | 3 城 / 10970 兵 | faction_2 | 3 城 / 11307 兵 | +0 | +337 | 37 | 21 / 3 / 253 |

## 診斷

### 動作分布 (基準線 vs 實驗組)

| 動作 | 基準線次數 | 實驗組次數 | 差異 |
| --- | --- | --- | --- |
| develop_agri | 80 | 74 | -6 |
| develop_commerce | 10 | 4 | -6 |
| develop_defense | 39 | 31 | -8 |
| move | 0 | 4 | +4 |
| recruit | 40 | 38 | -2 |
| rest | 110 | 121 | +11 |
| siege | 1 | 2 | +1 |

### 攻城勝敗 (出征 / siege_outcomes)

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 攻城嘗試 (siege attempts) | 1 | 2 | +1 |
| 成功攻克 (captured) | 0 | 0 | +0 |
| 擊退受挫 (repelled) | 1 | 2 | +1 |

### 出奔 / 抗旨 / 武將流失

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 出奔數 | 0 | 2 | +2 |
| 抗旨數 | 0 | 0 | +0 |
| 初始武將數 | 14 | 14 | +0 |
| 最終存活武將數 | 14.0 | 12.0 | -2.0 |
| 武將流失數 | 0.0 | 2.0 | +2.0 |
| 最終平均忠誠 | 88.7 | 10.8 | -78.0 |

### 被拒指令原因前 3 名

| 排名 | 原因 | 次數 |
| --- | --- | --- |
| 1 | `action 'develop_commerce' not legal` | 2 |
| 2 | `action 'develop_agri' not legal` | 1 |

### 點名與委任平均 (每回合)

| 類別 | 平均人數 |
| --- | --- |
| 點名執行 (Orders) | 1.05 |
| 系統委任 (Delegated) | 12.65 |

## 預算保護
- **max_calls**: 300
- **calls_used**: 14
- **stopped_early**: 否 (False)

## 錯誤樣本

1. `HTTP error 503: Service Unavailable {"error":{"message":"Service temporarily overloaded","type":"Service Unavailable","code":503}}`
2. `Request failed: TimeoutError: The read operation timed out`
3. `Backend circuit breaker is open after 5 consecutive errors. Last error: Request failed: TimeoutError: The read operation timed out`

## 限制說明與注意事項
> [!NOTE]
> **同座位比較、樣本數小時差異不具統計顯著性**。
>
> 1. **同座位比較之必要性**：各勢力在初始地緣、將領與兵力配置上存在結構性差異（例如 faction_1 曹操勢力結構上較強），不可直接比較各勢力勝率，必須比較同座位、同種子下 LLM 與規則 AI 的差異。
> 2. **統計顯著性**：SLG 模擬包含隨機事件與連鎖決策效應，當評測種子數量較少時，指標差異易受單局偶發狀況影響，不具統計顯著性。建議以較多種子（例如 20 個以上）進行正式評估。
