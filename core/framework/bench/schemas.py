"""
Benchmarking schemas.

Defines the core data structures for running agent benchmarks.
"""

from dataclasses import dataclass, field
from typing import Any, Literal
from pathlib import Path

@dataclass
class Scenario:
    """A single test scenario."""
    id: str
    description: str
    input_data: dict[str, Any]
    expected_outcome: dict[str, Any] | None = None
    max_retries: int = 0
    timeout_seconds: int = 60
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""
    agent_path: str
    scenarios: list[Scenario]
    output_dir: Path | None = None
    parallelism: int = 1
    iterations_per_scenario: int = 1

@dataclass
class ScenarioResult:
    """Result of a single scenario execution."""
    scenario_id: str
    iteration: int
    status: Literal["PASS", "FAIL", "ERROR"]
    duration_seconds: float
    output: Any | None = None
    error: str | None = None
    score: float | None = None  # 0.0 to 1.0
    feedback: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

@dataclass
class Scorecard:
    """Aggregated results for a benchmark run."""
    agent_name: str
    timestamp: str
    total_runs: int
    success_count: int
    failure_count: int
    error_count: int
    avg_latency: float
    results: list[ScenarioResult]
    
    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.success_count / self.total_runs
