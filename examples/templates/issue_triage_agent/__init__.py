"""
Issue Triage Agent - Triage GitHub issues with LLM-powered analysis.

Background pipeline fetches, analyzes, and scores issues against a vector
knowledge base while the user converses with the agent in real time.
"""

from .agent import (
    IssueTriageAgent,
    default_agent,
    goal,
    nodes,
    edges,
    async_entry_points,
    runtime_config,
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
    "async_entry_points",
    "runtime_config",
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
