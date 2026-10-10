"""Replaceable, untrusted AI plugins."""

from .backends import CommandCompleter, DemoCompleter, OpenAIChatCompleter, ScriptedCompleter
from .base import Agent, AgentError, FactionAgent
from .llm_agent import (
    Completer,
    LLMAgent,
    LLMFactionAgent,
    PlanParseError,
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_plan,
)
from .random_agent import RandomAgent
from .rule_based import RuleBasedAgent

__all__ = [
    "Agent",
    "AgentError",
    "CommandCompleter",
    "Completer",
    "DemoCompleter",
    "FactionAgent",
    "LLMAgent",
    "LLMFactionAgent",
    "OpenAIChatCompleter",
    "PlanParseError",
    "RandomAgent",
    "RuleBasedAgent",
    "SYSTEM_PROMPT",
    "ScriptedCompleter",
    "build_user_prompt",
    "parse_plan",
]
