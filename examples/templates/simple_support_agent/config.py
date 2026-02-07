"""Configuration for simple_support_agent."""

import os
from dataclasses import dataclass, field


def _load_preferred_model() -> str:
    """Load model from environment or use default."""
    return os.getenv("HIVE_DEFAULT_MODEL", "gpt-4o-mini")


@dataclass
class RuntimeConfig:
    model: str = field(default_factory=_load_preferred_model)
    temperature: float = 0.7
    max_tokens: int = 30000
    api_key: str | None = None
    api_base: str | None = None


default_config = RuntimeConfig()

metadata = {
    "name": "simple_support_agent",
    "description": "A basic customer support agent",
    "version": "1.0.0",
    "author": "Hive Composer",
}