"""Shared Hive configuration utilities.

Centralises reading of ~/.hive/configuration.json so that the runner
and every agent template share one implementation instead of copy-pasting
helper functions.

Supports auto-detection of LLM provider based on available API keys
in the environment (OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, etc.).
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
        with open(HIVE_CONFIG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Provider auto-detection
# ---------------------------------------------------------------------------

# Ordered list of (env_var, default_model) pairs.
# First key found in the environment wins.
_PROVIDER_DETECTION_ORDER: list[tuple[str, str]] = [
    ("ANTHROPIC_API_KEY", "anthropic/claude-sonnet-4-20250514"),
    ("OPENAI_API_KEY",    "openai/gpt-4.1-nano"),
    ("GEMINI_API_KEY",    "gemini/gemini-2.0-flash"),
    ("MISTRAL_API_KEY",   "mistral/mistral-small-latest"),
    ("GROQ_API_KEY",      "groq/llama-3.3-70b-versatile"),
    ("COHERE_API_KEY",    "cohere/command-r-plus"),
    ("TOGETHER_API_KEY",  "together/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"),
    ("CEREBRAS_API_KEY",  "cerebras/llama-3.3-70b"),
]

# Reverse mapping: env var name → env var name (for api_key lookup from model)
_MODEL_PREFIX_TO_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude":    "ANTHROPIC_API_KEY",
    "openai":    "OPENAI_API_KEY",
    "gpt-":      "OPENAI_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "google":    "GEMINI_API_KEY",
    "mistral":   "MISTRAL_API_KEY",
    "groq":      "GROQ_API_KEY",
    "cohere":    "COHERE_API_KEY",
    "together":  "TOGETHER_API_KEY",
    "cerebras":  "CEREBRAS_API_KEY",
    "ollama":    None,  # Local, no key needed
}


def _detect_provider_from_env() -> tuple[str, str] | None:
    """Detect which LLM provider is available based on environment API keys.

    Returns:
        Tuple of (model_string, api_key) if found, None otherwise.
    """
    for env_var, default_model in _PROVIDER_DETECTION_ORDER:
        key = os.environ.get(env_var)
        if key:
            return default_model, key
    return None


def get_api_key_for_model(model: str) -> str | None:
    """Get the API key environment variable value for a given model string.

    Args:
        model: LiteLLM model string (e.g. 'openai/gpt-4', 'anthropic/claude-3')

    Returns:
        The API key value if found in environment, None otherwise.
    """
    model_lower = model.lower()
    for prefix, env_var in _MODEL_PREFIX_TO_ENV.items():
        if model_lower.startswith(prefix):
            return os.environ.get(env_var) if env_var else None
    # Fallback: check OPENAI_API_KEY (many providers are OpenAI-compatible)
    return os.environ.get("OPENAI_API_KEY")


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------


def get_preferred_model() -> str:
    """Return the user's preferred LLM model string.

    Resolution order:
        1. Explicit config in ~/.hive/configuration.json (provider + model)
        2. Auto-detect from environment API keys (first available wins)
        3. Fallback to anthropic/claude-sonnet-4-20250514
    """
    # 1. Check explicit configuration
    llm = get_hive_config().get("llm", {})
    if llm.get("provider") and llm.get("model"):
        return f"{llm['provider']}/{llm['model']}"

    # 2. Auto-detect from environment
    detected = _detect_provider_from_env()
    if detected:
        return detected[0]

    # 3. Fallback
    return "anthropic/claude-sonnet-4-20250514"


def get_preferred_api_key() -> str | None:
    """Return the API key for the preferred model.

    Resolution order:
        1. Key matching the model in ~/.hive/configuration.json
        2. First available API key from environment
        3. None
    """
    # Check if explicit config points to a specific provider
    llm = get_hive_config().get("llm", {})
    if llm.get("provider") and llm.get("model"):
        model = f"{llm['provider']}/{llm['model']}"
        key = get_api_key_for_model(model)
        if key:
            return key

    # Auto-detect from environment
    detected = _detect_provider_from_env()
    if detected:
        return detected[1]

    return None


def get_max_tokens() -> int:
    """Return the configured max_tokens, falling back to DEFAULT_MAX_TOKENS."""
    return get_hive_config().get("llm", {}).get("max_tokens", DEFAULT_MAX_TOKENS)


# ---------------------------------------------------------------------------
# RuntimeConfig – shared across agent templates
# ---------------------------------------------------------------------------


@dataclass
class RuntimeConfig:
    """Agent runtime configuration.

    Reads from ~/.hive/configuration.json first, then auto-detects
    from environment API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY,
    GEMINI_API_KEY, etc.).
    """

    model: str = field(default_factory=get_preferred_model)
    temperature: float = 0.7
    max_tokens: int = field(default_factory=get_max_tokens)
    api_key: str | None = field(default_factory=get_preferred_api_key)
    api_base: str | None = None
