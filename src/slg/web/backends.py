"""Server-side AI opponent factory. Keys/URLs live on the server (env), never in the browser.

Environment:
  NVIDIA_API_KEY      key for the "nim" opponent (free NVIDIA NIM tier)
  SLG_NIM_MODEL       default nvidia/nemotron-3-super-120b-a12b
  SLG_QWEN_URL        OpenAI-compatible base URL of a Qwen server, e.g. https://<name>.trycloudflare.com/v1
  SLG_QWEN_MODEL      default qwen3.8:27b (Ollama tag); use the llama-server alias if you run llama.cpp
  SLG_QWEN_EXTRA_BODY JSON merged into each Qwen request (default switches thinking off for Ollama and llama.cpp)
  GEMINI_API_KEY      key for the "gemini" opponent

LLM opponents show the engine's siege verdict next to scouting ratios (it removed blind attacks in
docs/EVALUATION.md section 12) and retry rate limits / timeouts, which free tiers hit often.
"""

from __future__ import annotations

import json
import os

from ..agents.backends import CircuitBreakerCompleter, DemoCompleter, OpenAIChatCompleter
from ..agents.llm_agent import LLMFactionAgent
from ..agents.rule_based import RuleBasedAgent

KINDS = ("rule", "demo", "nim", "qwen", "gemini")

NIM_URL = "https://integrate.api.nvidia.com/v1"
NIM_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
QWEN_DEFAULT_EXTRA_BODY = {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": False}}
RETRIES = 4
TIMEOUT = 180.0


def _llm(base: OpenAIChatCompleter) -> LLMFactionAgent:
    return LLMFactionAgent(CircuitBreakerCompleter(base, max_consecutive_errors=3), siege_verdict=True)


def _qwen_extra_body() -> dict:
    raw = os.environ.get("SLG_QWEN_EXTRA_BODY")
    if not raw:
        return dict(QWEN_DEFAULT_EXTRA_BODY)
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("SLG_QWEN_EXTRA_BODY must be a JSON object")
    return body


def make_ai_agent(kind: str):
    if kind == "rule":
        return RuleBasedAgent("balanced")
    if kind == "demo":
        return LLMFactionAgent(CircuitBreakerCompleter(DemoCompleter(), max_consecutive_errors=3))
    if kind == "nim":
        return _llm(OpenAIChatCompleter(
            NIM_URL, os.environ.get("SLG_NIM_MODEL", NIM_DEFAULT_MODEL), api_key_env="NVIDIA_API_KEY",
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            http_retries=RETRIES, min_interval=1.0, timeout=TIMEOUT))
    if kind == "qwen":
        return _llm(OpenAIChatCompleter(
            os.environ.get("SLG_QWEN_URL", "http://127.0.0.1:8090/v1"), os.environ.get("SLG_QWEN_MODEL", "qwen3.8:27b"),
            extra_body=_qwen_extra_body(), http_retries=RETRIES, timeout=TIMEOUT))
    if kind == "gemini":
        return _llm(OpenAIChatCompleter(
            "https://generativelanguage.googleapis.com/v1beta/openai", os.environ.get("SLG_GEMINI_MODEL", "gemini-3.5-flash-lite"),
            api_key_env="GEMINI_API_KEY", http_retries=RETRIES, timeout=TIMEOUT))
    raise ValueError(f"unknown AI backend {kind!r}; choose from {KINDS}")
