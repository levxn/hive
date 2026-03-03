"""Agent graph construction for Issue Triage Agent.

Architecture (modelled after gmail_inbox_guardian):

  PRIMARY:  generic (self-loop, user converses forever)
  ASYNC:    intake -> fetch -> analyze -> dump -> (loop) -> report

Uses AgentRuntime for:
  - Multi-entry-point execution (primary + timer-driven)
  - Shared state: generic writes triage_config, pipeline reads it
  - Background execution: triage runs without blocking user conversation
  - Checkpointing for resume capability
"""

import os
from pathlib import Path

# Load .env from the agent directory so MCP subprocesses inherit env vars
try:
    from dotenv import load_dotenv

    _agent_dir = Path(__file__).parent.resolve()
    _env_path = _agent_dir / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)

    # Resolve relative CHROMA_PERSIST_DIR to absolute
    _chroma_dir = os.environ.get("CHROMA_PERSIST_DIR", "")
    if _chroma_dir and not os.path.isabs(_chroma_dir):
        os.environ["CHROMA_PERSIST_DIR"] = str(_agent_dir / _chroma_dir)
except ImportError:
    pass

from framework.graph import Constraint, EdgeCondition, EdgeSpec, Goal, SuccessCriterion
from framework.graph.checkpoint_config import CheckpointConfig
from framework.graph.edge import AsyncEntryPointSpec, GraphSpec
from framework.graph.executor import ExecutionResult
from framework.llm import LiteLLMProvider
from framework.runner.tool_registry import ToolRegistry
from framework.runtime.agent_runtime import AgentRuntime, AgentRuntimeConfig, create_agent_runtime
from framework.runtime.execution_stream import EntryPointSpec

from .config import default_config, metadata
from .nodes import (
    generic_node,
    intake_node,
    fetch_node,
    analyze_node,
    dump_node,
    report_node,
)

# ---------------------------------------------------------------------------
# Goal
# ---------------------------------------------------------------------------
goal = Goal(
    id="issue-triage",
    name="Issue Triage Agent",
    description=(
        "Triage GitHub issues using LLM-powered novelty and severity analysis, "
        "maintain a vector knowledge base for deduplication, and send categorized "
        "HTML email digests to maintainers. Runs as a background pipeline while "
        "the user converses with the agent."
    ),
    success_criteria=[
        SuccessCriterion(
            id="sc-fetch-issues",
            description="Correctly fetches and filters GitHub issues within the requested time window",
            metric="issues_fetched",
            target=">=1",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-novelty-analysis",
            description="Performs novelty and severity analysis comparing each issue against the vector knowledge base",
            metric="novelty_analysis_performed",
            target="true",
            weight=0.25,
        ),
        SuccessCriterion(
            id="sc-knowledge-base",
            description="Upserts analyzed issues into the vector knowledge base for future deduplication",
            metric="knowledge_base_updated",
            target="true",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-digest-delivery",
            description="Sends an email digest when high-value issues are found and email is requested",
            metric="digest_sent",
            target="true",
            weight=0.2,
        ),
        SuccessCriterion(
            id="sc-stale-detection",
            description="Identifies assigned issues with no activity for 14+ days",
            metric="stale_detection_run",
            target="true",
            weight=0.15,
        ),
    ],
    constraints=[
        Constraint(
            id="c-no-fabrication",
            description="Never fabricate issue data, URLs, or analysis results",
            constraint_type="hard",
            category="quality",
        ),
        Constraint(
            id="c-source-accuracy",
            description="All issue numbers, titles, and URLs must come from actual GitHub API responses",
            constraint_type="hard",
            category="quality",
        ),
        Constraint(
            id="c-email-safety",
            description="Only send email when explicitly requested by the user",
            constraint_type="hard",
            category="safety",
        ),
        Constraint(
            id="c-shared-config",
            description=(
                "Triage config must persist in shared memory so timer-triggered "
                "pipeline runs can access it without re-asking the user"
            ),
            constraint_type="hard",
            category="architectural",
        ),
    ],
)

# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
nodes = [
    generic_node,
    intake_node,
    fetch_node,
    analyze_node,
    dump_node,
    report_node,
]

# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------
edges = [
    # PRIMARY FLOW: generic self-loop (user stays here forever)
    EdgeSpec(
        id="generic-to-generic",
        source="generic",
        target="generic",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
        description="Self-loop: user keeps chatting after setting config",
    ),

    # ASYNC PIPELINE: intake -> fetch (candidates exist)
    EdgeSpec(
        id="intake-to-fetch",
        source="intake",
        target="fetch",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('issue_queue') is not None",
        priority=1,
        description="Candidates found -- start per-issue processing loop",
    ),
    # ASYNC PIPELINE: intake -> report (no candidates, skip loop)
    EdgeSpec(
        id="intake-to-report",
        source="intake",
        target="report",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('triage_results') is not None",
        priority=1,
        description="No candidates -- skip loop, go to report",
    ),

    # ASYNC PIPELINE: per-issue loop
    EdgeSpec(
        id="fetch-to-analyze",
        source="fetch",
        target="analyze",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
        description="Issue content fetched -- score against ChromaDB",
    ),
    EdgeSpec(
        id="analyze-to-dump",
        source="analyze",
        target="dump",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
        description="Issue scored -- upsert to ChromaDB",
    ),
    EdgeSpec(
        id="dump-to-fetch",
        source="dump",
        target="fetch",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('issue_queue') is not None",
        priority=-1,
        description="More issues -- loop back to fetch next one",
    ),
    EdgeSpec(
        id="dump-to-report",
        source="dump",
        target="report",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('triage_results') is not None",
        priority=1,
        description="All issues processed -- present results",
    ),
]

# ---------------------------------------------------------------------------
# Graph configuration
# ---------------------------------------------------------------------------
entry_node = "generic"
entry_points = {"start": "generic"}
async_entry_points = [
    AsyncEntryPointSpec(
        id="triage-timer",
        name="Scheduled Triage Run",
        entry_node="intake",
        trigger_type="timer",
        trigger_config={"interval_minutes": 5},
        isolation_level="shared",
        max_concurrent=1,
    ),
]
pause_nodes = []
terminal_nodes = []
conversation_mode = "continuous"
identity_prompt = (
    "You are an issue triage assistant. You help maintainers triage GitHub issues "
    "by analyzing novelty and severity against a knowledge base, detecting stale "
    "issues, and sending email digests -- all running in the background."
)
runtime_config = AgentRuntimeConfig(
    webhook_host="127.0.0.1",
    webhook_port=8080,
    webhook_routes=[],
)

# Module-level config for AgentRunner.load()
loop_config = {
    "max_iterations": 500,
    "max_tool_calls_per_turn": 100,
    "max_history_tokens": 64000,
    "max_tool_result_chars": 30000,
}


class IssueTriageAgent:
    """
    Issue Triage Agent -- event-driven triage with background pipeline.

    Primary:  generic (self-loop, user converses forever)
    Async:    intake -> fetch -> analyze -> dump -> (loop) -> report

    Entry Points:
    - "start" (primary): User chats, sets triage config via generic node
    - "triage-timer" (timer): Scheduled triage run every 5 minutes

    Uses AgentRuntime for:
    - Multi-entry-point execution (primary + timer-driven)
    - Shared state for config persistence across entry points
    - Background execution without blocking user conversation
    - Checkpointing for resume capability
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
        self._graph: GraphSpec | None = None
        self._agent_runtime: AgentRuntime | None = None
        self._tool_registry: ToolRegistry | None = None
        self._storage_path: Path | None = None

    def _build_graph(self) -> GraphSpec:
        """Build the GraphSpec."""
        return GraphSpec(
            id="issue-triage-graph",
            goal_id=self.goal.id,
            version="1.0.0",
            entry_node=self.entry_node,
            entry_points=self.entry_points,
            terminal_nodes=self.terminal_nodes,
            pause_nodes=self.pause_nodes,
            nodes=self.nodes,
            edges=self.edges,
            default_model=self.config.model,
            max_tokens=self.config.max_tokens,
            loop_config={
                "max_iterations": 500,
                "max_tool_calls_per_turn": 100,
                "max_history_tokens": 64000,
                "max_tool_result_chars": 30000,
            },
            conversation_mode="continuous",
            identity_prompt=identity_prompt,
            async_entry_points=[
                AsyncEntryPointSpec(
                    id="triage-timer",
                    name="Scheduled Triage Run",
                    entry_node="intake",
                    trigger_type="timer",
                    trigger_config={"interval_minutes": 5},
                    isolation_level="shared",
                    max_concurrent=1,
                ),
            ],
        )

    def _setup(self, mock_mode=False) -> None:
        """Set up the agent runtime with sessions, checkpoints, and logging."""
        self._storage_path = Path.home() / ".hive" / "agents" / "issue_triage_agent"
        self._storage_path.mkdir(parents=True, exist_ok=True)

        self._tool_registry = ToolRegistry()

        mcp_config_path = Path(__file__).parent / "mcp_servers.json"
        if mcp_config_path.exists():
            self._tool_registry.load_mcp_config(mcp_config_path)

        llm = None
        if not mock_mode:
            llm = LiteLLMProvider(
                model=self.config.model,
                api_key=self.config.api_key,
                api_base=self.config.api_base,
            )

        tool_executor = self._tool_registry.get_executor()
        tools = list(self._tool_registry.get_tools().values())

        self._graph = self._build_graph()

        checkpoint_config = CheckpointConfig(
            enabled=True,
            checkpoint_on_node_start=False,
            checkpoint_on_node_complete=True,
            checkpoint_max_age_days=7,
            async_checkpoint=True,
        )

        entry_point_specs = [
            # Primary entry point (user-facing conversation)
            EntryPointSpec(
                id="default",
                name="Issue Triage Chat",
                entry_node=self.entry_node,
                trigger_type="manual",
                isolation_level="shared",
            ),
            # Scheduled triage pipeline (runs in background)
            EntryPointSpec(
                id="triage-timer",
                name="Scheduled Triage Run",
                entry_node="intake",
                trigger_type="timer",
                trigger_config={"interval_minutes": 5},
                isolation_level="shared",
                max_concurrent=1,
            ),
        ]

        self._agent_runtime = create_agent_runtime(
            graph=self._graph,
            goal=self.goal,
            storage_path=self._storage_path,
            entry_points=entry_point_specs,
            llm=llm,
            tools=tools,
            tool_executor=tool_executor,
            checkpoint_config=checkpoint_config,
            config=runtime_config,
        )

    async def start(self, mock_mode=False) -> None:
        """Set up and start the agent runtime."""
        if self._agent_runtime is None:
            self._setup(mock_mode=mock_mode)
        if not self._agent_runtime.is_running:
            await self._agent_runtime.start()

    async def stop(self) -> None:
        """Stop the agent runtime and clean up."""
        if self._agent_runtime and self._agent_runtime.is_running:
            await self._agent_runtime.stop()
        self._agent_runtime = None

    async def trigger_and_wait(
        self,
        entry_point: str = "default",
        input_data: dict | None = None,
        timeout: float | None = None,
        session_state: dict | None = None,
    ) -> ExecutionResult | None:
        """Execute the graph and wait for completion."""
        if self._agent_runtime is None:
            raise RuntimeError("Agent not started. Call start() first.")

        return await self._agent_runtime.trigger_and_wait(
            entry_point_id=entry_point,
            input_data=input_data or {},
            session_state=session_state,
        )

    async def run(self, context: dict, mock_mode=False, session_state=None) -> ExecutionResult:
        """Run the agent (convenience method for single execution)."""
        await self.start(mock_mode=mock_mode)
        try:
            result = await self.trigger_and_wait("default", context, session_state=session_state)
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
            "client_facing_nodes": [n.id for n in self.nodes if n.client_facing],
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
default_agent = IssueTriageAgent()
