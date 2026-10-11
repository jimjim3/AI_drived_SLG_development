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
from .backends import ConfigError
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
    "出征前請比較 frontier 中敵城的 troops 與 defense，並參考 cast 中的 siege_odds"
    "（勝算比 = 攻方戰力 ÷ 守方戰力（不含隨機）；實戰有約 ±15% 的隨機，比值低於 1.3 的出征很可能失敗並損失大量兵力，"
    "除非有特殊理由否則不要出征；也可以選擇徵兵、開發或移動等待時機）；出征會抽走本城守軍。\n"
    "【參數格式】\n"
    "params 的鍵名必須與該武將 legal 清單中的鍵名完全相同；值為單一字串或數字，不可為陣列。"
    "legal 清單中若標示 to=[a,b]，表示 to 只能取 a 或 b 其中一個，不可為陣列。\n"
    "範例：\n"
    '- 移動：{"officer":"<officer_id>","action":"move","params":{"to":"<city_id>"},"memo":"…"}\n'
    '- 攻城：{"officer":"<officer_id>","action":"siege","params":{"to":"<city_id>","troops":<troops>},"memo":"…"}\n'
    '- 徵兵：{"officer":"<officer_id>","action":"recruit","params":{"troops":<troops>},"memo":"…"}\n'
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


TO_ALIASES = ("target", "destination", "dest", "city", "target_city")
TROOPS_ALIASES = ("troop", "soldiers", "army", "num_troops")


def parse_plan(raw: str, stats: dict[str, int] | None = None) -> FactionPlan:
    """Parse raw LLM response text into a validated FactionPlan."""
    fence_start = raw.find("```")
    search_from = 0
    if fence_start != -1:
        nl = raw.find("\n", fence_start)
        search_from = nl + 1 if nl != -1 else fence_start + 3

    decoder = json.JSONDecoder()
    brace = raw.find("{", search_from)
    bracket = raw.find("[", search_from)

    data = None
    # If an array starts before the first brace, check if top-level was meant to be a list
    if bracket != -1 and (brace == -1 or bracket < brace):
        try:
            val, _ = decoder.raw_decode(raw, bracket)
            if not isinstance(val, dict):
                raise PlanParseError(f"頂層必須為 dict，實際為 {type(val).__name__}")
            data = val
        except json.JSONDecodeError:
            data = None

    if data is None:
        if brace == -1:
            if bracket != -1:
                try:
                    val, _ = decoder.raw_decode(raw, bracket)
                except json.JSONDecodeError as exc:
                    raise PlanParseError(f"JSON 語法錯誤：{exc}") from exc
                if not isinstance(val, dict):
                    raise PlanParseError(f"頂層必須為 dict，實際為 {type(val).__name__}")
                data = val
            else:
                raise PlanParseError("未找到 JSON 物件（缺少 '{' 或 '}'）")
        else:
            try:
                data, _ = decoder.raw_decode(raw, brace)
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

    normalized_orders_count = 0
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

        order_normalized = False
        params_specified = "params" in item and item["params"] is not None
        if not params_specified:
            params_raw: dict[str, object] = {}
            for fk in ("to", "troops", *TO_ALIASES, *TROOPS_ALIASES):
                if fk in item:
                    params_raw[fk] = item[fk]
                    order_normalized = True
        else:
            p_val = item["params"]
            if not isinstance(p_val, dict):
                raise PlanParseError(f"order #{idx} 的 'params' 須為 dict，實際為 {type(p_val).__name__}")
            params_raw = dict(p_val)
            if not params_raw:
                for fk in ("to", "troops", *TO_ALIASES, *TROOPS_ALIASES):
                    if fk in item:
                        params_raw[fk] = item[fk]
                        order_normalized = True

        # Alias normalization for 'to'
        to_present = "to" in params_raw
        aliases_to_found = [a for a in TO_ALIASES if a in params_raw]
        if aliases_to_found:
            order_normalized = True
            if not to_present:
                params_raw["to"] = params_raw[aliases_to_found[0]]
            for a in aliases_to_found:
                del params_raw[a]

        # Alias normalization for 'troops'
        troops_present = "troops" in params_raw
        aliases_troops_found = [a for a in TROOPS_ALIASES if a in params_raw]
        if aliases_troops_found:
            order_normalized = True
            if not troops_present:
                params_raw["troops"] = params_raw[aliases_troops_found[0]]
            for a in aliases_troops_found:
                del params_raw[a]

        params: dict[str, object] = {}
        for k, v in params_raw.items():
            if isinstance(v, (list, tuple)):
                if len(v) == 1:
                    v = v[0]
                    order_normalized = True
            if isinstance(v, float) and v.is_integer():
                params[k] = int(v)
            else:
                params[k] = v

        if order_normalized:
            normalized_orders_count += 1

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

    if stats is not None:
        stats["normalized_params"] = stats.get("normalized_params", 0) + normalized_orders_count

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
            "normalized_params": 0,
        }
        self.errors_seen: list[str] = []

    def _record_error(self, msg: str) -> None:
        sample = msg[:300]
        if sample not in self.errors_seen and len(self.errors_seen) < 5:
            self.errors_seen.append(sample)

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
            except ConfigError as exc:
                self.usage["calls"] -= 1
                self.usage["prompt_chars"] -= prompt_chars
                self._record_error(str(exc))
                raise
            except Exception as exc:
                self.usage["errors"] += 1
                last_error = str(exc)
                self._record_error(str(exc))
                continue

            self.usage["response_chars"] += len(raw)

            try:
                stats: dict[str, int] = {}
                plan = parse_plan(raw, stats=stats)
                self.usage["normalized_params"] += stats.get("normalized_params", 0)
                return plan
            except PlanParseError as exc:
                self.usage["parse_failures"] += 1
                last_error = str(exc)
                self._record_error(f"parse: {exc}")

        raise AgentError(f"LLM 決策失敗（重試耗盡）：{last_error}")


# Backward compatibility alias
LLMAgent = LLMFactionAgent
