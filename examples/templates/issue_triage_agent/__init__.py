"""
Issue Triage Agent — Triage GitHub issues with LLM-powered analysis.

Monitors a GitHub repository, analyzes issue novelty and severity against
a vector knowledge base, identifies high-value issues, detects stale
assignments, and sends categorized HTML email digests to maintainers.
"""

from .agent import (
    IssueTriageAgent,
    default_agent,
    goal,
    nodes,
    edges,
    conversation_mode,
    loop_config,
    entry_node,
    entry_points,
    pause_nodes,
    terminal_nodes,
)
from .config import RuntimeConfig, AgentMetadata, default_config, metadata

__version__ = "1.0.0"

__all__ = [
    "IssueTriageAgent",
    "default_agent",
    "goal",
    "nodes",
    "edges",
    "conversation_mode",
    "loop_config",
    "entry_node",
    "entry_points",
    "pause_nodes",
    "terminal_nodes",
    "RuntimeConfig",
    "AgentMetadata",
    "default_config",
    "metadata",
]
