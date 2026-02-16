"""Shared Hive configuration utilities.

Centralises reading of ~/.hive/configuration.json so that the runner
and every agent template share one implementation instead of copy-pasting
helper functions.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from framework.graph.edge import DEFAULT_MAX_TOKENS

# ---------------------------------------------------------------------------
# Low-level config file access
# ---------------------------------------------------------------------------

HIVE_CONFIG_FILE = Path.home() / ".hive" / "configuration.json"


def get_hive_config() -> dict[str, Any]:
    """Load hive configuration from ~/.hive/configuration.json."""
    if not HIVE_CONFIG_FILE.exists():
        return {}
    try:
        with open(HIVE_CONFIG_FILE, encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------


def get_preferred_model() -> str:
    """Return the user's preferred LLM model string (e.g. 'anthropic/claude-sonnet-4-20250514').

    Priority:
    1. Explicit config in ~/.hive/configuration.json
    2. Auto-detect from available API keys in environment
    3. Fall back to anthropic/claude-sonnet-4-20250514
    """
    llm = get_hive_config().get("llm", {})
    if llm.get("provider") and llm.get("model"):
        return f"{llm['provider']}/{llm['model']}"

    # Auto-detect from available API keys
    _KEY_TO_MODEL = {
        "ANTHROPIC_API_KEY": "anthropic/claude-sonnet-4-20250514",
        "OPENAI_API_KEY": "gpt-4.1-nano",
        "GEMINI_API_KEY": "gemini/gemini-2.0-flash",
        "GROQ_API_KEY": "groq/llama-3.3-70b-versatile",
        "CEREBRAS_API_KEY": "cerebras/llama-3.3-70b",
        "MISTRAL_API_KEY": "mistral/mistral-large-latest",
        "DEEPSEEK_API_KEY": "deepseek/deepseek-chat",
        "TOGETHER_API_KEY": "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
    }
    for env_var, model in _KEY_TO_MODEL.items():
        if os.environ.get(env_var):
            return model

    return "anthropic/claude-sonnet-4-20250514"


def get_max_tokens() -> int:
    """Return the configured max_tokens, falling back to DEFAULT_MAX_TOKENS."""
    return get_hive_config().get("llm", {}).get("max_tokens", DEFAULT_MAX_TOKENS)


def get_api_key() -> str | None:
    """Return the API key from the environment variable specified in configuration."""
    llm = get_hive_config().get("llm", {})
    api_key_env_var = llm.get("api_key_env_var")
    if api_key_env_var:
        return os.environ.get(api_key_env_var)
    return None


# ---------------------------------------------------------------------------
# RuntimeConfig – shared across agent templates
# ---------------------------------------------------------------------------


@dataclass
class RuntimeConfig:
    """Agent runtime configuration loaded from ~/.hive/configuration.json."""

    model: str = field(default_factory=get_preferred_model)
    temperature: float = 0.7
    max_tokens: int = field(default_factory=get_max_tokens)
    api_key: str | None = field(default_factory=get_api_key)
    api_base: str | None = None
