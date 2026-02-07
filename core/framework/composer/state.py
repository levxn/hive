"""Composer state management - Pydantic models for the agent being built."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class NodeData(BaseModel):
    """Node definition for agent graph."""
    
    id: str
    name: str
    description: str | None = None
    system_prompt: str = "You are a helpful assistant."
    tools: list[str] = []
    node_type: str = "event_loop"
    client_facing: bool = False
    input_keys: list[str] = []
    output_keys: list[str] = []


class EdgeData(BaseModel):
    """Represents an edge between nodes."""

    source: str
    target: str
    condition: Literal["always", "on_success", "on_failure"] = "on_success"


class GoalData(BaseModel):
    """Agent goal definition."""

    id: str
    name: str
    description: str
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class ComposerState(BaseModel):
    """Complete state of the agent being composed."""

    agent_name: str = ""
    agent_description: str = ""
    output_path: Path | None = None
    
    goal: GoalData | None = None
    nodes: list[NodeData] = Field(default_factory=list)
    edges: list[EdgeData] = Field(default_factory=list)
    
    entry_node: str | None = None
    terminal_nodes: list[str] = Field(default_factory=list)
    
    # Configuration
    default_model: str = "gpt-4o-mini"
    max_tokens: int = 30000
    
    # Tool configuration
    selected_tools: list[str] = Field(default_factory=list)

    def is_complete(self) -> bool:
        """Check if the state has minimum required data."""
        return bool(
            self.agent_name
            and self.goal
            and self.nodes
            and self.entry_node
        )

    def get_node_by_id(self, node_id: str) -> NodeData | None:
        """Get a node by its ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
