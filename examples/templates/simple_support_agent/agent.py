"""simple_support_agent agent definition."""

from framework.graph import EdgeSpec, EdgeCondition, Goal, SuccessCriterion, Constraint
from framework.graph.edge import GraphSpec
from framework.graph.executor import ExecutionResult, GraphExecutor
from framework.runtime.event_bus import EventBus
from framework.runtime.core import Runtime
from framework.llm import LiteLLMProvider
from framework.runner.tool_registry import ToolRegistry

from .config import default_config, metadata
from .nodes import (    intake_node,    response_node,)

# Goal definition
goal = Goal(
    id="support_goal",
    name="Customer Support Goal",
    description="Provide helpful responses to customer inquiries",
    success_criteria=[        SuccessCriterion(
            metric="response_quality",
            target="completion",
            description="response_quality"
        ),        SuccessCriterion(
            metric="resolution_speed",
            target="completion",
            description="resolution_speed"
        ),    ],
    constraints=[    ],
)

# Nodes
nodes = [    intake_node,    response_node,]

# Edges
edges = [    EdgeSpec(
        source="intake",
        target="response",
        condition=EdgeCondition.ON_SUCCESS,
    ),]

# Entry point
entry_node = "intake"

# Terminal nodes
terminal_nodes = [    "response",]


class Agent:
    """simple_support_agent - A basic customer support agent"""

    def __init__(self, model: str | None = None):
        self.model = model or default_config.model
        self.graph_spec = GraphSpec(
            id="support_goal-graph",
            goal_id=goal.id,
            version=metadata["version"],
            entry_node=entry_node,
            terminal_nodes=terminal_nodes,
            nodes=nodes,
            edges=edges,
            max_tokens=default_config.max_tokens,
        )
        
        # Create components
        self.llm_provider = LiteLLMProvider(
            model=self.model,
            temperature=default_config.temperature,
        )
        self.tool_registry = ToolRegistry()
        self.event_bus = EventBus()
        
        # Build runtime and executor
        self.runtime = Runtime(
            goal=goal,
            llm_provider=self.llm_provider,
            tool_registry=self.tool_registry,
            event_bus=self.event_bus,
        )
        
        self.executor = GraphExecutor(
            graph=self.graph_spec,
            runtime=self.runtime,
        )

    async def run(self, context: dict) -> ExecutionResult:
        """Execute the agent with the given context."""
        return await self.executor.execute(context)