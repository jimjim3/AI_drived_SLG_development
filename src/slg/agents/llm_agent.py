"""LLM-backed faction agent.

Performs faction-level decision making: exactly one LLM call per faction per turn.
Uses structured JSON output to produce orders, chronicle, and next_cast spotlight.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Callable, ClassVar

from ..schema import (
    CHRONICLE_MAX,
    MEMO_MAX,
    AgentDecision,
    FactionPlan,
)
from .base import AgentError, FactionAgent

if TYPE_CHECKING:
    from ..engine.view import FactionView

Completer = Callable[[str, str], str]

SYSTEM_PROMPT = (
    "你是勢力的謀主。每位出場武將每回合至多一個行動。"
    "行動只能取自該武將 legal 清單，參數須在範圍內。"
    "金錢與兵力有限、指令依序結算（先列者先扣）。"
    "未被點名的武將由系統委任。"
    "久未被點名（且動作非 rest）的武將忠誠會下降並可能出奔，忠誠低者可能抗旨；請輪流關注全體武將。"
    "輸出只能是一個 JSON 物件，格式如下：\n"
    '{"orders":[{"officer":"<id>","action":"<動作>","params":{},"memo":"≤20字奏摺"}],'
    '"chronicle":"≤300字，以史官口吻記述上回合結果與本回合決策",'
    '"next_cast":["<id>",...]}\n'
    "不得輸出 JSON 以外文字。"
)


def build_user_prompt(view: FactionView, error: str | None = None) -> str:
    """Build the per-turn user prompt from a FactionView, appending error if retrying."""
    prompt = "狀態：" + json.dumps(view.to_dict(), ensure_ascii=False, separators=(",", ":"))
    if error is not None:
        prompt += f"\n上次輸出無法使用：{error}。請只輸出修正後的 JSON。"
    return prompt


class PlanParseError(ValueError):
    """Raised when raw LLM response cannot be parsed into a FactionPlan."""


def parse_plan(raw: str) -> FactionPlan:
    """Parse raw LLM response text into a validated FactionPlan."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise PlanParseError("未找到 JSON 物件（缺少 '{' 或 '}'）")

    json_str = raw[start : end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise PlanParseError(f"JSON 語法錯誤：{exc}") from exc

    if not isinstance(data, dict):
        raise PlanParseError(f"頂層必須為 dict，實際為 {type(data).__name__}")

    if "orders" in data:
        raw_orders = data["orders"]
        if not isinstance(raw_orders, list):
            raise PlanParseError(f"'orders' 須為 list，實際為 {type(raw_orders).__name__}")
    else:
        raw_orders = []

    orders: list[AgentDecision] = []
    for idx, item in enumerate(raw_orders):
        if not isinstance(item, dict):
            raise PlanParseError(f"order #{idx} 須為 dict，實際為 {type(item).__name__}")

        officer = item.get("officer")
        if officer is None:
            officer = item.get("officer_id")
        if not isinstance(officer, str) or not officer:
            raise PlanParseError(f"order #{idx} 缺少有效的 'officer'（或 'officer_id'）字串")

        action = item.get("action")
        if not isinstance(action, str) or not action:
            raise PlanParseError(f"order #{idx} 缺少有效的 'action' 字串")

        params_raw = item.get("params", {})
        if not isinstance(params_raw, dict):
            raise PlanParseError(f"order #{idx} 的 'params' 須為 dict，實際為 {type(params_raw).__name__}")

        params: dict[str, object] = {}
        for k, v in params_raw.items():
            if isinstance(v, float) and v.is_integer():
                params[k] = int(v)
            else:
                params[k] = v

        memo_raw = item.get("memo", "")
        memo = str(memo_raw)[:MEMO_MAX]

        orders.append(AgentDecision(officer_id=officer, action=action, params=params, memo=memo))

    chronicle_raw = data.get("chronicle", "")
    chronicle = str(chronicle_raw)[:CHRONICLE_MAX]

    if "next_cast" in data:
        raw_next_cast = data["next_cast"]
        if not isinstance(raw_next_cast, list):
            raise PlanParseError(f"'next_cast' 須為 list，實際為 {type(raw_next_cast).__name__}")
        for idx, item in enumerate(raw_next_cast):
            if not isinstance(item, str):
                raise PlanParseError(f"'next_cast' #{idx} 須為字串，實際為 {type(item).__name__}")
        next_cast = tuple(raw_next_cast[:12])
    else:
        next_cast = ()

    return FactionPlan(orders=tuple(orders), chronicle=chronicle, next_cast=next_cast)


class LLMFactionAgent(FactionAgent):
    name: ClassVar[str] = "llm"

    def __init__(
        self,
        completer: Completer,
        system_prompt: str = SYSTEM_PROMPT,
        max_retries: int = 1,
    ) -> None:
        self._completer = completer
        self._system_prompt = system_prompt
        self._max_retries = max_retries
        self.usage: dict[str, int] = {
            "calls": 0,
            "prompt_chars": 0,
            "response_chars": 0,
            "parse_failures": 0,
            "errors": 0,
        }

    def decide(self, view: FactionView) -> FactionPlan:
        last_error: str | None = None
        max_attempts = 1 + self._max_retries

        for _ in range(max_attempts):
            user_prompt = build_user_prompt(view, error=last_error)
            prompt_chars = len(self._system_prompt) + len(user_prompt)

            self.usage["calls"] += 1
            self.usage["prompt_chars"] += prompt_chars

            try:
                raw = self._completer(self._system_prompt, user_prompt)
            except Exception as exc:
                self.usage["errors"] += 1
                last_error = str(exc)
                continue

            self.usage["response_chars"] += len(raw)

            try:
                return parse_plan(raw)
            except PlanParseError as exc:
                self.usage["parse_failures"] += 1
                last_error = str(exc)

        raise AgentError(f"LLM 決策失敗（重試耗盡）：{last_error}")


# Backward compatibility alias
LLMAgent = LLMFactionAgent
