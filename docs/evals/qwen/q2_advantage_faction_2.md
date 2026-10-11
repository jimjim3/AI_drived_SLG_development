# SLG 勢力決策評測報告 (LLM 對規則 AI 基準線)

## 評測設定
- **評測席位 (Seat)**: `faction_2`
- **情境 (Scenario)**: `advantage`
- **評測種子數**: 計畫種子 10 個，實際完成 10 個 (種子: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`)
- **呼叫預算 (Max Calls)**: 300
- **已使用呼叫數 (Calls Used)**: 202 (未觸發提前終止)

## 評測摘要

| 指標 | 數值 |
| --- | --- |
| 評測席位 (seat) | faction_2 |
| 基準線勝率 (baseline_win_rate) | 100.0% |
| 實驗組勝率 (experiment_win_rate) | 90.0% |
| 勝率差異 (win_rate_delta) | -10.0% |
| 平均城池差 (mean_cities_delta) | +0.70 |
| 平均兵力差 (mean_troops_delta) | +848.6 |
| 指令接受率 (orders_accept_rate) | 90.2% |
| 計劃失敗率 (plan_failure_rate) | 1.0% |
| 每回合委任數 (delegated_per_turn) | 8.80 |
| LLM 呼叫次數 (calls) | 202 |
| 估計 Token 數 (est_tokens) | 476745 |
| 解析失敗次數 (parse_failures) | 0 |
| 呼叫錯誤次數 (errors) | 4 |

**可能原因提示**：表現正常，未見明顯異常。

## 逐種子明細

| 種子 | 基準勝者 | 基準城數/兵力 | 實驗勝者 | 實驗城數/兵力 | 城池差 | 兵力差 | 呼叫數 | 成功/被拒/委任 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | faction_2 | 3 城 / 10970 兵 | faction_2 | 4 城 / 13406 兵 | +1 | +2436 | 20 | 112 / 8 / 168 |
| 1 | faction_2 | 3 城 / 12210 兵 | faction_2 | 4 城 / 13868 兵 | +1 | +1658 | 21 | 106 / 8 / 174 |
| 2 | faction_2 | 3 城 / 10990 兵 | faction_2 | 3 城 / 10279 兵 | +0 | -711 | 21 | 96 / 18 / 184 |
| 3 | faction_2 | 3 城 / 13550 兵 | faction_2 | 4 城 / 13020 兵 | +1 | -530 | 20 | 99 / 15 / 181 |
| 4 | faction_2 | 3 城 / 12239 兵 | faction_2 | 4 城 / 15310 兵 | +1 | +3071 | 20 | 107 / 7 / 173 |
| 5 | faction_2 | 3 城 / 11790 兵 | faction_2 | 4 城 / 15217 兵 | +1 | +3427 | 20 | 110 / 10 / 170 |
| 6 | faction_2 | 3 城 / 13450 兵 | faction_2 | 4 城 / 14636 兵 | +1 | +1186 | 20 | 102 / 6 / 178 |
| 7 | faction_2 | 3 城 / 10910 兵 | faction_2 | 3 城 / 10987 兵 | +0 | +77 | 20 | 95 / 19 / 185 |
| 8 | faction_2 | 3 城 / 10950 兵 | faction_3 | 3 城 / 9734 兵 | +0 | -1216 | 20 | 98 / 16 / 182 |
| 9 | faction_2 | 3 城 / 13350 兵 | faction_2 | 4 城 / 12438 兵 | +1 | -912 | 20 | 114 / 6 / 166 |

## 診斷

### 動作分布 (基準線 vs 實驗組)

| 動作 | 基準線次數 | 實驗組次數 | 差異 |
| --- | --- | --- | --- |
| develop_agri | 772 | 821 | +49 |
| develop_commerce | 79 | 257 | +178 |
| develop_defense | 359 | 436 | +77 |
| move | 0 | 4 | +4 |
| recruit | 407 | 333 | -74 |
| rest | 1176 | 939 | -237 |
| siege | 7 | 10 | +3 |

### 攻城勝敗 (出征 / siege_outcomes)

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 攻城嘗試 (siege attempts) | 7 | 10 | +3 |
| 成功攻克 (captured) | 0 | 7 | +7 |
| 擊退受挫 (repelled) | 7 | 3 | -4 |

### 出奔 / 抗旨 / 武將流失

| 指標 | 基準線 | 實驗組 | 差異 |
| --- | --- | --- | --- |
| 出奔數 | 0 | 0 | +0 |
| 抗旨數 | 0 | 0 | +0 |
| 初始武將數 | 14 | 14 | +0 |
| 最終存活武將數 | 14.0 | 14.0 | +0.0 |
| 武將流失數 | 0.0 | 0.0 | +0.0 |
| 最終平均忠誠 | 88.7 | 82.2 | -6.5 |

### 被拒指令原因前 3 名

| 排名 | 原因 | 次數 |
| --- | --- | --- |
| 1 | `action 'develop_commerce' not legal` | 43 |
| 2 | `action 'develop_agri' not legal` | 21 |
| 3 | `action 'develop_defense' not legal` | 19 |

### 點名與委任平均 (每回合)

| 類別 | 平均人數 |
| --- | --- |
| 點名執行 (Orders) | 5.20 |
| 系統委任 (Delegated) | 8.80 |

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
