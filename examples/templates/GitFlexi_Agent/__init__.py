"""
GitFlexi Agent - Monitors GitHub for new issues, analyzes for novelty,
and sends email digests of important updates.
"""

from .agent import GitFlexiAgent, default_agent, goal, nodes, edges
from .config import RuntimeConfig, AgentMetadata, default_config, metadata, settings

__version__ = "1.0.0"

__all__ = [
    "GitFlexiAgent",
    "default_agent",
    "goal",
    "nodes",
    "edges",
    "RuntimeConfig",
    "AgentMetadata",
    "default_config",
    "metadata",
    "settings",
]
