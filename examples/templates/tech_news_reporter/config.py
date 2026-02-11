"""Runtime configuration."""

import os
from dataclasses import dataclass

from framework.config import RuntimeConfig


def get_runtime_config() -> RuntimeConfig:
    """Get the runtime configuration with fallback logic."""
    # Fallback: If Anthropic key is missing but OpenAI key exists, use OpenAI
    if "ANTHROPIC_API_KEY" not in os.environ and "OPENAI_API_KEY" in os.environ:
        print(
            "Warning by config.py: ANTHROPIC_API_KEY not found. "
            "Falling back to OpenAI (gpt-4.1-nano)."
        )
        return RuntimeConfig(model="openai/gpt-4.1-nano")
    
    return RuntimeConfig()


default_config = get_runtime_config()


@dataclass
class AgentMetadata:
    name: str = "Tech & AI News Reporter"
    version: str = "1.0.0"
    description: str = (
        "Research the latest technology and AI news from the web, "
        "summarize key stories, and produce a well-organized report "
        "for the user to read."
    )


metadata = AgentMetadata()
