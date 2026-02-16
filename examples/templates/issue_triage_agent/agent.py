"""Agent graph construction for Issue Triage Agent."""

import os
from pathlib import Path

# Load .env from the agent directory so MCP subprocesses inherit env vars
# (GITHUB_TOKEN, GITHUB_REPO_OWNER, SMTP_*, OPENAI_API_KEY, etc.)
try:
    from dotenv import load_dotenv

    _agent_dir = Path(__file__).parent.resolve()
    _env_path = _agent_dir / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)

    # Resolve relative CHROMA_PERSIST_DIR to absolute (relative to agent dir,
    # not the MCP subprocess cwd which is the tools/ directory)
    _chroma_dir = os.environ.get("CHROMA_PERSIST_DIR", "")
    if _chroma_dir and not os.path.isabs(_chroma_dir):
        os.environ["CHROMA_PERSIST_DIR"] = str(_agent_dir / _chroma_dir)
except ImportError:
    pass  # python-dotenv not installed; user must export env vars manually

from framework.graph import EdgeSpec, EdgeCondition, Goal, SuccessCriterion, Constraint
from framework.graph.edge import GraphSpec
from framework.graph.executor import ExecutionResult, GraphExecutor
from framework.runtime.event_bus import EventBus
from framework.runtime.core import Runtime
from framework.llm import LiteLLMProvider
from framework.runner.tool_registry import ToolRegistry

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
        "HTML email digests to maintainers."
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
# Edges — linear pipeline with loop-back for forever-alive
# ---------------------------------------------------------------------------
edges = [
    # generic -> intake: user wants to run a task
    EdgeSpec(
        id="generic-to-intake",
        source="generic",
        target="intake",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
        description="User wants to run a task — collect config and fetch issues",
    ),
    # intake -> fetch: candidates exist, start per-issue loop
    EdgeSpec(
        id="intake-to-fetch",
        source="intake",
        target="fetch",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('issue_queue') is not None",
        priority=1,
        description="Candidates found — start per-issue processing loop",
    ),
    # intake -> report: no candidates, skip loop
    EdgeSpec(
        id="intake-to-report",
        source="intake",
        target="report",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('triage_results') is not None",
        priority=1,
        description="No candidates — skip loop, go to report",
    ),
    # fetch -> analyze: content fetched for one issue
    EdgeSpec(
        id="fetch-to-analyze",
        source="fetch",
        target="analyze",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
        description="Issue content fetched — score against ChromaDB",
    ),
    # analyze -> dump: issue scored, upsert to ChromaDB
    EdgeSpec(
        id="analyze-to-dump",
        source="analyze",
        target="dump",
        condition=EdgeCondition.ON_SUCCESS,
        priority=1,
        description="Issue scored — upsert to ChromaDB",
    ),
    # dump -> fetch: more issues to process (FEEDBACK LOOP)
    EdgeSpec(
        id="dump-to-fetch",
        source="dump",
        target="fetch",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('issue_queue') is not None",
        priority=-1,
        description="More issues — loop back to fetch next one",
    ),
    # dump -> report: all issues processed (FORWARD)
    EdgeSpec(
        id="dump-to-report",
        source="dump",
        target="report",
        condition=EdgeCondition.CONDITIONAL,
        condition_expr="output.get('triage_results') is not None",
        priority=1,
        description="All issues processed — present results",
    ),
    # report -> generic: loop back for another task
    EdgeSpec(
        id="report-to-generic",
        source="report",
        target="generic",
        condition=EdgeCondition.ON_SUCCESS,
        priority=-1,
        description="Loop back to generic for more conversation or another task",
    ),
]

# ---------------------------------------------------------------------------
# Graph configuration
# ---------------------------------------------------------------------------
entry_node = "generic"
entry_points = {"start": "generic"}
pause_nodes = []
terminal_nodes = []  # Forever-alive: loops back to intake

# Module-level config read by AgentRunner.load() when building GraphSpec
conversation_mode = "continuous"
loop_config = {
    "max_iterations": 500,
    "max_tool_calls_per_turn": 100,
    "max_history_tokens": 64000,
    "max_tool_result_chars": 30000,
}


class IssueTriageAgent:
    """
    Issue Triage Agent — 6-node pipeline with per-issue processing loop.

    Flow: generic -> intake -> fetch -> analyze -> dump -> fetch (loop)
                                                       -> report -> generic

    generic: conversational entry, routes to intake when user wants to act
    intake:  collect mode/lookback/email, dual-fetch ALL issues, filter, stale detection
    fetch:   for ONE issue: get body, comments, timeline, linked PRs
    analyze: for ONE issue: search ChromaDB, score novelty/severity/impact
    dump:    for ONE issue: upsert to ChromaDB, loop back to fetch or go to report
    report:  present results, send email digest
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
            conversation_mode="continuous",
            loop_config={
                "max_iterations": 500,
                "max_tool_calls_per_turn": 100,
                "max_history_tokens": 64000,
                "max_tool_result_chars": 30000,
            },
        )

    def _setup(self) -> GraphExecutor:
        """Set up the executor with all components."""
        from pathlib import Path

        storage_path = Path.home() / ".hive" / "agents" / "issue_triage_agent"
        storage_path.mkdir(parents=True, exist_ok=True)

        self._event_bus = EventBus()
        self._tool_registry = ToolRegistry()

        mcp_config_path = Path(__file__).parent / "mcp_servers.json"
        if mcp_config_path.exists():
            self._tool_registry.load_mcp_config(mcp_config_path)

        llm = LiteLLMProvider(
            model=self.config.model,
            api_key=self.config.api_key,
            api_base=self.config.api_base,
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

        # Check that forever-alive graph has no dead-end nodes
        if not self.terminal_nodes:
            sources = {e.source for e in self.edges}
            for node in self.nodes:
                if node.id not in sources:
                    warnings.append(
                        f"Node '{node.id}' has no outgoing edge in a forever-alive graph"
                    )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }


# Create default instance
default_agent = IssueTriageAgent()
