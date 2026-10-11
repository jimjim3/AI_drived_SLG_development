# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)

## 評測設定
- **評測席位 (Seat)**: `faction_3`
- **評測種子數**: 計畫種子 10 個，實際完成 10 個 (種子: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`)
- **呼叫預算 (Max Calls)**: 300
- **已使用呼叫數 (Calls Used)**: 202 (未觸發提前終止)

## 評測摘要

| 指標 | 數值 |
| --- | --- |
| 評測席位 (seat) | faction_3 |
| 基準線勝率 (baseline_win_rate) | 0.0% |
| 實驗組勝率 (experiment_win_rate) | 100.0% |
| 勝率差異 (win_rate_delta) | +100.0% |
| 平均城池差 (mean_cities_delta) | +0.00 |
| 平均兵力差 (mean_troops_delta) | +2698.0 |
| 指令接受率 (orders_accept_rate) | 81.2% |
| 計劃失敗率 (plan_failure_rate) | 0.5% |
| 每回合委任數 (delegated_per_turn) | 9.38 |
| LLM 呼叫次數 (calls) | 202 |
| 估計 Token 數 (est_tokens) | 453916 |
| 解析失敗次數 (parse_failures) | 0 |
| 呼叫錯誤次數 (errors) | 3 |

**可能原因提示**：指令被拒比例偏高，主因：action 'develop_defense' not legal

## 逐種子明細

| 種子 | 基準勝者 | 基準城數/兵力 | 實驗勝者 | 實驗城數/兵力 | 城池差 | 兵力差 | 呼叫數 | 成功/被拒/委任 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | faction_1 | 3 城 / 10800 兵 | faction_3 | 3 城 / 12230 兵 | +0 | +1430 | 20 | 87 / 26 / 193 |
| 1 | faction_1 | 3 城 / 10200 兵 | faction_3 | 3 城 / 13100 兵 | +0 | +2900 | 20 | 105 / 14 / 175 |
| 2 | faction_1 | 3 城 / 10700 兵 | faction_3 | 3 城 / 12700 兵 | +0 | +2000 | 20 | 95 / 13 / 185 |
| 3 | faction_1 | 3 城 / 10200 兵 | faction_3 | 3 城 / 13200 兵 | +0 | +3000 | 20 | 90 / 24 / 190 |
| 4 | faction_1 | 3 城 / 10200 兵 | faction_3 | 3 城 / 13000 兵 | +0 | +2800 | 21 | 93 / 15 / 187 |
| 5 | faction_1 | 3 城 / 9800 兵 | faction_3 | 3 城 / 12800 兵 | +0 | +3000 | 21 | 86 / 22 / 194 |
| 6 | faction_1 | 3 城 / 10200 兵 | faction_3 | 3 城 / 12400 兵 | +0 | +2200 | 20 | 98 / 21 / 182 |
| 7 | faction_1 | 3 城 / 9900 兵 | faction_3 | 3 城 / 13650 兵 | +0 | +3750 | 20 | 89 / 31 / 191 |
| 8 | faction_1 | 3 城 / 10300 兵 | faction_3 | 3 城 / 12800 兵 | +0 | +2500 | 20 | 94 / 20 / 186 |
| 9 | faction_1 | 3 城 / 9800 兵 | faction_3 | 3 城 / 13200 兵 | +0 | +3400 | 20 | 86 / 28 / 194 |

## 診斷

### 動作分布 (基準線 vs 實驗組)

| 動作 | 基準線次數 | 實驗組次數 | 差異 |
| --- | --- | --- | --- |
| develop_agri | 641 | 755 | +114 |
| develop_commerce | 70 | 289 | +219 |
| develop_defense | 360 | 410 | +50 |
| move | 0 | 1 | +1 |
| recruit | 456 | 429 | -27 |
| rest | 1273 | 916 | -357 |

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
| 最終平均忠誠 | 83.6 | 80.1 | -3.6 |

### 被拒指令原因前 3 名

| 排名 | 原因 | 次數 |
| --- | --- | --- |
| 1 | `action 'develop_defense' not legal` | 48 |
| 2 | `action 'develop_agri' not legal` | 43 |
| 3 | `param troops=N out of range [N, N]` | 36 |

### 點名與委任平均 (每回合)

| 類別 | 平均人數 |
| --- | --- |
| 點名執行 (Orders) | 4.62 |
| 系統委任 (Delegated) | 9.38 |

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
