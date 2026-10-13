"""Server-side AI opponent factory. Keys/URLs live on the server (env), never in the browser."""

from __future__ import annotations

import os

from ..agents.backends import CircuitBreakerCompleter, DemoCompleter, OpenAIChatCompleter
from ..agents.llm_agent import LLMFactionAgent
from ..agents.rule_based import RuleBasedAgent

KINDS = ("rule", "demo", "qwen", "gemini")


def make_ai_agent(kind: str):
    if kind == "rule":
        return RuleBasedAgent("balanced")
    if kind == "demo":
        return LLMFactionAgent(CircuitBreakerCompleter(DemoCompleter(), max_consecutive_errors=3))
    if kind == "qwen":
        base = OpenAIChatCompleter(
            os.environ.get("SLG_QWEN_URL", "http://127.0.0.1:8090/v1"), os.environ.get("SLG_QWEN_MODEL", "qwen3.8-27b"),
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        return LLMFactionAgent(CircuitBreakerCompleter(base, max_consecutive_errors=3))
    if kind == "gemini":
        base = OpenAIChatCompleter(
            "https://generativelanguage.googleapis.com/v1beta/openai", os.environ.get("SLG_GEMINI_MODEL", "gemini-3.5-flash-lite"),
            api_key_env="GEMINI_API_KEY")
        return LLMFactionAgent(CircuitBreakerCompleter(base, max_consecutive_errors=3))
    raise ValueError(f"unknown AI backend {kind!r}; choose from {KINDS}")
