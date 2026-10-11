# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)

## 評測設定
- **評測席位 (Seat)**: `faction_2`
- **評測種子數**: 計畫種子 10 個，實際完成 10 個 (種子: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`)
- **呼叫預算 (Max Calls)**: 300
- **已使用呼叫數 (Calls Used)**: 202 (未觸發提前終止)

## 評測摘要

| 指標 | 數值 |
| --- | --- |
| 評測席位 (seat) | faction_2 |
| 基準線勝率 (baseline_win_rate) | 0.0% |
| 實驗組勝率 (experiment_win_rate) | 0.0% |
| 勝率差異 (win_rate_delta) | +0.0% |
| 平均城池差 (mean_cities_delta) | +0.00 |
| 平均兵力差 (mean_troops_delta) | -507.0 |
| 指令接受率 (orders_accept_rate) | 84.5% |
| 計劃失敗率 (plan_failure_rate) | 0.5% |
| 每回合委任數 (delegated_per_turn) | 9.46 |
| LLM 呼叫次數 (calls) | 202 |
| 估計 Token 數 (est_tokens) | 461232 |
| 解析失敗次數 (parse_failures) | 0 |
| 呼叫錯誤次數 (errors) | 3 |

**可能原因提示**：指令被拒比例偏高，主因：action 'develop_commerce' not legal

## 逐種子明細

| 種子 | 基準勝者 | 基準城數/兵力 | 實驗勝者 | 實驗城數/兵力 | 城池差 | 兵力差 | 呼叫數 | 成功/被拒/委任 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | faction_1 | 3 城 / 10000 兵 | faction_1 | 3 城 / 9288 兵 | +0 | -712 | 20 | 83 / 19 / 197 |
| 1 | faction_1 | 3 城 / 9800 兵 | faction_1 | 3 城 / 8771 兵 | +0 | -1029 | 20 | 96 / 18 / 184 |
| 2 | faction_1 | 3 城 / 9700 兵 | faction_1 | 3 城 / 10431 兵 | +0 | +731 | 20 | 89 / 19 / 191 |
| 3 | faction_1 | 3 城 / 10000 兵 | faction_1 | 3 城 / 9416 兵 | +0 | -584 | 20 | 92 / 10 / 188 |
| 4 | faction_1 | 3 城 / 10000 兵 | faction_1 | 3 城 / 10088 兵 | +0 | +88 | 20 | 88 / 20 / 192 |
| 5 | faction_1 | 3 城 / 9900 兵 | faction_1 | 3 城 / 8896 兵 | +0 | -1004 | 21 | 94 / 14 / 186 |
| 6 | faction_1 | 3 城 / 9600 兵 | faction_1 | 3 城 / 10490 兵 | +0 | +890 | 21 | 93 / 9 / 187 |
| 7 | faction_1 | 3 城 / 9800 兵 | faction_1 | 3 城 / 7697 兵 | +0 | -2103 | 20 | 94 / 20 / 186 |
| 8 | faction_1 | 3 城 / 10100 兵 | faction_1 | 3 城 / 9173 兵 | +0 | -927 | 20 | 94 / 20 / 186 |
| 9 | faction_1 | 3 城 / 10200 兵 | faction_1 | 3 城 / 9780 兵 | +0 | -420 | 20 | 85 / 17 / 195 |

## 診斷

### 動作分布 (基準線 vs 實驗組)

| 動作 | 基準線次數 | 實驗組次數 | 差異 |
| --- | --- | --- | --- |
| develop_agri | 597 | 497 | -100 |
| develop_commerce | 108 | 248 | +140 |
| develop_defense | 464 | 520 | +56 |
| move | 0 | 4 | +4 |
| recruit | 401 | 409 | +8 |
| rest | 1230 | 1122 | -108 |

### 攻城勝敗 (出征 / siege_outcomes)

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 攻城嘗試 (siege attempts) | 0 | 0 | +0 |
| 成功攻克 (captured) | 0 | 0 | +0 |
| 擊退受挫 (repelled) | 0 | 0 | +0 |

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
| 1 | `action 'develop_commerce' not legal` | 58 |
| 2 | `action 'develop_defense' not legal` | 34 |
| 3 | `action 'recruit' not legal` | 29 |

### 點名與委任平均 (每回合)

| 類別 | 平均人數 |
| --- | --- |
| 點名執行 (Orders) | 4.54 |
| 系統委任 (Delegated) | 9.46 |

## 預算保護
- **max_calls**: 300
- **calls_used**: 202
- **stopped_early**: 否 (False)

## 錯誤樣本

1. `Command failed with exit code 1: n _read_status
    line = str(self.fp.readline(_MAXLINE + 1), "iso-8859-1")
               ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
  File "/home/yhho3.winbond/.conda/lib/python3.14/socket.py", line 729, in readinto
    return self._sock.recv_into(b)
           ~~~~~~~~~~~~~~~`
2. `Command failed with exit code 1: n _read_status
    line = str(self.fp.readline(_MAXLINE + 1), "iso-8859-1")
               ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
  File "/home/yhho3.winbond/.conda/lib/python3.14/socket.py", line 729, in readinto
    return self._sock.recv_into(b)
           ~~~~~~~~~~~~~~~`

## 限制說明與注意事項
> [!NOTE]
> **同座位比較、樣本數小時差異不具統計顯著性**。
>
> 1. **同座位比較之必要性**：各勢力在初始地緣、將領與兵力配置上存在結構性差異（例如 faction_1 曹操勢力結構上較強），不可直接比較各勢力勝率，必須比較同座位、同種子下 LLM 與規則 AI 的差異。
> 2. **統計顯著性**：SLG 模擬包含隨機事件與連鎖決策效應，當評測種子數量較少時，指標差異易受單局偶發狀況影響，不具統計顯著性。建議以較多種子（例如 20 個以上）進行正式評估。
