"""LLM agent adapter: wraps an injectable completer behind the Agent interface.

The agent receives a ``completer: Callable[[str], str]`` that is called with a
JSON prompt string and expected to return a JSON response string. No network
calls or third-party SDKs are used; the caller is responsible for providing
the actual LLM backend.
"""

from __future__ import annotations

import json
from typing import Any, Callable, ClassVar

from ..schema import AgentDecision, GameState, LegalAction, OfficerState, ParamSpec
from .base import Agent

CompleterCallable = Callable[[str], str]


def _param_spec_to_schema(spec: ParamSpec) -> dict[str, Any]:
    if spec.is_discrete():
        return {"type": "string", "enum": list(spec.choices)}
    schema: dict[str, Any] = {"type": "number"}
    if spec.min is not None:
        schema["minimum"] = spec.min
    if spec.max is not None:
        schema["maximum"] = spec.max
    if spec.step is not None:
        schema["multipleOf"] = spec.step
    return schema


def _legal_action_to_dict(la: LegalAction) -> dict[str, Any]:
    return {
        "action": la.action,
        "params": {name: _param_spec_to_schema(spec) for name, spec in la.params.items()},
        "note": la.note,
    }


def build_prompt(
    state: GameState,
    officer: OfficerState,
    legal: list[LegalAction],
) -> str:
    prompt = {
        "instruction": (
            f"Choose one action for officer '{officer.name}' "
            f"(id: {officer.officer_id}) in city '{officer.city_id}' "
            f"for faction '{officer.faction_id}' on turn {state.turn}. "
            f"Return a JSON object with 'action' and 'params' keys."
        ),
        "legal_actions": [_legal_action_to_dict(la) for la in legal],
    }
    return json.dumps(prompt, ensure_ascii=False)


class LLMAgent(Agent):
    name: ClassVar[str] = "llm"

    def __init__(self, completer: CompleterCallable) -> None:
        self._completer = completer

    def decide(
        self,
        state: GameState,
        officer: OfficerState,
        legal: list[LegalAction],
    ) -> AgentDecision:
        prompt = build_prompt(state, officer, legal)
        raw = self._completer(prompt)
        return self._parse(officer, raw)

    @staticmethod
    def _parse(officer: OfficerState, raw: str) -> AgentDecision:
        try:
            data = json.loads(raw)
            if isinstance(data, str):
                data = json.loads(data)
            if not isinstance(data, dict):
                raise ValueError(f"expected dict, got {type(data).__name__}")

            if "tool_calls" in data:
                tc = data["tool_calls"][0]
                func = tc["function"]
                args = func["arguments"]
                data = json.loads(args) if isinstance(args, str) else args
                if not isinstance(data, dict):
                    raise ValueError("tool-call arguments not a dict")

            action = data.get("action")
            if not isinstance(action, str):
                raise ValueError(f"missing or invalid 'action': {action!r}")

            params = data.get("params", {})
            if not isinstance(params, dict):
                raise ValueError(f"'params' must be a dict, got {type(params).__name__}")

            return AgentDecision(
                officer_id=officer.officer_id,
                action=action,
                params=params,
            )
        except (json.JSONDecodeError, ValueError, KeyError, IndexError, TypeError):
            return AgentDecision(officer_id=officer.officer_id, action="invalid", params={})
