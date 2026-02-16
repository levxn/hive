"""Agent graph for GitFlexi Agent."""

from pathlib import Path

from framework.graph import EdgeSpec, EdgeCondition, Goal, GraphSpec
from framework.graph.executor import ExecutionResult, GraphExecutor
from framework.runtime.core import Runtime
from framework.runtime.event_bus import EventBus
from framework.llm import LiteLLMProvider
from framework.runner.tool_registry import ToolRegistry

from .config import default_config, metadata, settings
from .nodes import monitor_node, triage_node, reporter_node

# 0. Setup Environment for Tools
# Propagate settings to env vars for tools (email_tool, github_tool)
import os
if settings.github_token:
    os.environ["GITHUB_TOKEN"] = settings.github_token
if settings.smtp_host:
    os.environ["SMTP_HOST"] = settings.smtp_host
if settings.smtp_port:
    os.environ["SMTP_PORT"] = str(settings.smtp_port)
if settings.smtp_username:
    os.environ["SMTP_USERNAME"] = settings.smtp_username
if settings.smtp_password:
    os.environ["SMTP_PASSWORD"] = settings.smtp_password
if settings.email_from:
    os.environ["EMAIL_FROM"] = settings.email_from
elif settings.notification_email:
     # Fallback: send from the notification email if no specific sender configured
    os.environ["EMAIL_FROM"] = settings.notification_email

# 1. Define Goal
goal = Goal(
    id="git-flexi-monitor",
    name="GitFlexi Maintainer",
    description=metadata.description,
    success_criteria=[],
    constraints=[]
)

# 2. Define Nodes
nodes = [
    monitor_node,
    triage_node,
    reporter_node
]

# 3. Define Edges
edges = [
    EdgeSpec(
        id="monitor-to-triage",
        source="monitor",
        target="triage",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1
    ),
    EdgeSpec(
        id="triage-to-reporter",
        source="triage",
        target="reporter",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1
    )
]

# 4. Graph Config
entry_node = "monitor"
entry_points = {"start": "monitor"}
pause_nodes = []
terminal_nodes = ["reporter"]


class GitFlexiAgent:
    """
    GitFlexi Agent - Monitors GitHub, Triages Issues, Reports Updates.

    Flow: monitor -> triage -> reporter
    All nodes are event_loop type — LLM-driven with tools.
    """

    def __init__(self, config=None):
        self.config = config or default_config
        self.goal = goal
        self.nodes = nodes
        self.edges = edges
        self.entry_node = entry_node
        self.entry_points = entry_points
        self.pause_nodes = pause_nodes
        self.terminal_nodes = terminal_nodes
        self._executor: GraphExecutor | None = None
        self._graph: GraphSpec | None = None
        self._event_bus: EventBus | None = None
        self._tool_registry: ToolRegistry | None = None

    def _build_graph(self) -> GraphSpec:
        return GraphSpec(
            id="GitFlexi_Agent-graph",
            goal_id=self.goal.id,
            version=metadata.version,
            entry_node=self.entry_node,
            entry_points=self.entry_points,
            terminal_nodes=self.terminal_nodes,
            pause_nodes=self.pause_nodes,
            nodes=self.nodes,
            edges=self.edges,
            default_model=self.config.model,
            max_tokens=self.config.max_tokens,
            loop_config={
                "max_iterations": 50,
                "max_tool_calls_per_turn": 10,
                "max_history_tokens": 32000,
            }
        )

    def _setup(self) -> GraphExecutor:
        # Settings are now propagated at module level (lines 16-30)
        
        storage_path = settings.storage_dir
        storage_path.mkdir(parents=True, exist_ok=True)

        self._event_bus = EventBus()
        self._tool_registry = ToolRegistry()

        mcp_config_path = Path(__file__).parent / "mcp_servers.json"
        if mcp_config_path.exists():
            self._tool_registry.load_mcp_config(mcp_config_path)

        llm = LiteLLMProvider(
            model=self.config.model,
            api_key=self.config.api_key,
            api_base=self.config.api_base
        )

        tool_executor = self._tool_registry.get_executor()
        tools = list(self._tool_registry.get_tools().values())

        self._graph = self._build_graph()
        runtime = Runtime(storage_path)

        self._executor = GraphExecutor(
            runtime=runtime,
            llm=llm,
            tools=tools,
            tool_executor=tool_executor,
            event_bus=self._event_bus,
            storage_path=storage_path,
            loop_config=self._graph.loop_config,
        )

        return self._executor

    async def start(self) -> None:
        """Set up the agent (initialize executor and tools)."""
        if self._executor is None:
            self._setup()

    async def stop(self) -> None:
        """Clean up resources."""
        self._executor = None
        self._event_bus = None

    async def trigger_and_wait(
        self,
        entry_point: str,
        input_data: dict,
        timeout: float | None = None,
        session_state: dict | None = None,
    ) -> ExecutionResult | None:
        """Execute the graph and wait for completion."""
        if self._executor is None:
            raise RuntimeError("Agent not started. Call start() first.")
        if self._graph is None:
            raise RuntimeError("Graph not built. Call start() first.")

        return await self._executor.execute(
            graph=self._graph,
            goal=self.goal,
            input_data=input_data,
            session_state=session_state,
        )

    async def run(self, context: dict, session_state=None) -> ExecutionResult:
        """Run the agent (convenience method for single execution)."""
        await self.start()
        try:
            result = await self.trigger_and_wait(
                "start", context, session_state=session_state
            )
            return result or ExecutionResult(success=False, error="Execution timeout")
        finally:
            await self.stop()

    def info(self):
        """Get agent information."""
        return {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "goal": {
                "name": self.goal.name,
                "description": self.goal.description,
            },
            "nodes": [n.id for n in self.nodes],
            "edges": [e.id for e in self.edges],
            "entry_node": self.entry_node,
            "entry_points": self.entry_points,
            "pause_nodes": self.pause_nodes,
            "terminal_nodes": self.terminal_nodes,
        }

    def validate(self):
        """Validate agent structure."""
        errors = []
        warnings = []

        node_ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge {edge.id}: source '{edge.source}' not found")
            if edge.target not in node_ids:
                errors.append(f"Edge {edge.id}: target '{edge.target}' not found")

        if self.entry_node not in node_ids:
            errors.append(f"Entry node '{self.entry_node}' not found")

        for terminal in self.terminal_nodes:
            if terminal not in node_ids:
                errors.append(f"Terminal node '{terminal}' not found")

        for ep_id, node_id in self.entry_points.items():
            if node_id not in node_ids:
                errors.append(
                    f"Entry point '{ep_id}' references unknown node '{node_id}'"
                )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


# Create default instance
default_agent = GitFlexiAgent()
