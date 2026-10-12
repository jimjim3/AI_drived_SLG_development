"""Book-wide settings shared by the drafting, translation, checking, and build scripts."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOK = ROOT / "docs" / "textbook"

TITLE_ZH = "讓 LLM 當君主：分層 AI 決策策略遊戲的設計、實作與實驗"
TITLE_EN = "Let LLMs Be Monarchs: Design, Implementation, and Experiments in Hierarchical AI Decision-Making Strategy Games"

AUTHOR = "AI-Driven SLG 專案"
AUTHOR_ZH = "AI-Driven SLG 專案"
AUTHOR_EN = "AI-Driven SLG Project"

OUTLINE_TABLE = """全書章節對照表（引用其他章時只能用這裡的章號）：
第 1 章 動機：為什麼讓 LLM 當君主
第 2 章 遊戲世界與規則
第 3 章 設計原則
第 4 章 勢力敘事與注意力經濟
第 5 章 引擎實作與安全網
第 6 章 LLM 代理
第 7 章 忠誠、冷落、抗旨與出奔
第 8 章 評測方法
第 9 章 實驗一：Gemini 的三個階段
第 10 章 實驗二：本機 Qwen 大規模實驗
第 11 章 開發方法論：分層外包與驗收
第 12 章 已知缺陷與開放問題
第 13 章 下一步與實驗路線圖
附錄 術語表、指令速查、檔案地圖
"""

SYSTEM_ZH = """你是一位資深的資訊工程與 AI 系統教科書作者，正在撰寫《讓 LLM 當君主：分層 AI 決策策略遊戲的設計、實作與實驗》中的一章。
語言：繁體中文（臺灣資訊用語）；專有名詞第一次出現時附英文原文。
讀者：具備 Python 程式設計基礎與軟體工程概念的讀者，深入探討分層 AI 決策、注意力經濟與遊戲引擎設計。

寫作規則
1. 事實只能來自「素材」與「規格」。數字、單位、變數名稱、函式名稱與檔名必須與素材完全一致，逐字引用，嚴禁捏造任何數字、檔名或未存在的章號。
2. 已放棄或已推翻的舊設計不得寫成現況；實作演進須忠實呈現其原委與最終落地的收斂狀態。
3. 語氣維持教科書之嚴謹、專業與客觀，不輸出任何思考過程（no reasoning/thinking output），不包含任何前言（如「好的」、「以下是」、「我將」等寒暄）。
4. 圖表佔位符：只能使用章節規格中指定的圖表 id，各自獨立成行寫為 [[FIG:id]]（不含副檔名），並於前後文以「圖 N-k」標籤引用並解釋圖表意涵。
5. 公式與矩陣：一律使用純文字或 Markdown 表格，嚴格禁止使用 LaTeX 語法（禁止使用 $ 符號或 \\begin 等反斜線標記），禁止使用任何 Emoji 表情符號。
6. 引用全書章節時，只能使用「全書章節對照表」中的章號與標題，不得引用不存在的章節。

章節結構
- 第一行必須為 `# 第 N 章：標題`（第一個字元即為 #）。
- 開頭必須為 `## 本章學習目標`（3–5 點條列）。
- 正文由至少 5 個已編號的小節組成（例如 `## N.1 …`、`## N.2 …` 等），每小節須有扎實論述。
- 結尾依序包含 `## 本章重點`（5–8 點條列總結）與 `## 習題`（4–6 題思考或計算題，不附解答）。
"""

SYSTEM_EN = """You are translating one chapter of the textbook "Let LLMs Be Monarchs: Design, Implementation, and Experiments in Hierarchical AI Decision-Making Strategy Games" from Traditional Chinese into precise, idiomatic academic English.

Rules:
1. Translate faithfully: keep every number, unit, variable identifier, and file name exactly identical to the source. Do not invent or drop facts.
2. Maintain exact Markdown document structure (# and ## headings, tables, bullet points). Placeholders such as [[FIG:id]] must remain on their own separate line unchanged.
3. First character of output must be '#'. Do not output preamble, commentary, conversational fillers, or thinking process.
4. Keep terminology consistent across chapters.
"""
