"""Runtime configuration for Issue Triage Agent."""

from dataclasses import dataclass

from framework.config import RuntimeConfig

default_config = RuntimeConfig()


@dataclass
class AgentMetadata:
    name: str = "Issue Triage Agent"
    version: str = "1.0.0"
    description: str = (
        "Triage GitHub issues using LLM-powered novelty and severity analysis, "
        "maintain a vector-based knowledge base for deduplication, and send "
        "categorized HTML email digests to maintainers."
    )
    intro_message: str = (
        "Hi! I'm your Issue Triage Agent for the adenhq/hive repository.\n\n"
        "I can answer questions about what I do, or run tasks for you:\n"
        "1. **Triage recent issues** — Analyze novelty & severity, email a digest.\n"
        "2. **Check for stale issues** — Find inactive assigned issues.\n\n"
        "What would you like to know or do?"
    )


metadata = AgentMetadata()
