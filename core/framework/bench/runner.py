"""
Benchmark Runner.

Orchestrates the execution of agent benchmarks.
"""

import asyncio
import time
import importlib.util
from pathlib import Path
from typing import Any
import sys

from .schemas import BenchmarkConfig, Scenario, ScenarioResult, Scorecard
from .scorer import BasicScorer

class BenchmarkRunner:
    """Runs benchmarks for a given agent configuration."""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.scorer = BasicScorer()

    async def run(self) -> Scorecard:
        """Run all scenarios and generate a scorecard."""
        results : list[ScenarioResult] = []
        
        # Load agent class (dynamically import from path)
        agent_class = self._load_agent_class(self.config.agent_path)
        
        # Determine concurrency semaphore
        sem = asyncio.Semaphore(self.config.parallelism)

        async def _run_single_scenario(scenario: Scenario, iteration: int):
            async with sem:
                return await self._execute_scenario(agent_class, scenario, iteration)

        tasks = []
        for scenario in self.config.scenarios:
            for i in range(1, self.config.iterations_per_scenario + 1):
                tasks.append(_run_single_scenario(scenario, i))
        
        results = await asyncio.gather(*tasks)
        
        return self._generate_scorecard(results)

    async def _execute_scenario(self, AgentClass: type, scenario: Scenario, iteration: int) -> ScenarioResult:
        """Execute a single scenario iteration."""
        start_time = time.time()
        try:
            # Instantiate agent (assuming standard interface)
            # This is a key assumption: Agents must be instantiable without args or via config
            agent = AgentClass()
            
            # Execute agent (assuming .run(context) interface)
            if hasattr(agent, "run"):
                output = await agent.run(context=scenario.input_data)
            else:
                raise ValueError(f"Agent class {AgentClass.__name__} does not have a 'run' method.")
            
            duration = time.time() - start_time
            
            # Score the result
            return self.scorer.score(
                scenario=scenario, 
                output=output, 
                duration=duration,
                iteration=iteration
            )

        except Exception as e:
            duration = time.time() - start_time
            return ScenarioResult(
                scenario_id=scenario.id,
                iteration=iteration,
                status="ERROR",
                duration_seconds=duration,
                error=str(e),
                score=0.0
            )

    def _generate_scorecard(self, results: list[ScenarioResult]) -> Scorecard:
        """Aggregate results into a scorecard."""
        total = len(results)
        success = sum(1 for r in results if r.status == "PASS")
        failure = sum(1 for r in results if r.status == "FAIL")
        error = sum(1 for r in results if r.status == "ERROR")
        
        avg_latency = 0.0
        if total > 0:
            avg_latency = sum(r.duration_seconds for r in results) / total
            
        return Scorecard(
            agent_name=Path(self.config.agent_path).name,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            total_runs=total,
            success_count=success,
            failure_count=failure,
            error_count=error,
            avg_latency=avg_latency,
            results=results
        )

    def _load_agent_class(self, agent_path: str) -> type:
        """Dynamically load the agent class from the given path."""
        path = Path(agent_path).resolve()
        
        # Check if it's a directory
        if path.is_dir():
            script_path = path / "agent.py"
        else:
            script_path = path

        if not script_path.exists():
            raise FileNotFoundError(f"Agent script not found at {script_path}")

        # Logic to handle package structure (relative imports support)
        # Walk up from script_path to find the root of the package
        current_dir = script_path.parent
        package_parts = []
        
        while (current_dir / "__init__.py").exists():
            package_parts.insert(0, current_dir.name)
            current_dir = current_dir.parent
            
        # current_dir is now the directory containing the top-level package
        root_path = str(current_dir)
        
        # Add root path to sys.path if not present
        if root_path not in sys.path:
            sys.path.insert(0, root_path)

        try:
            if package_parts:
                # It's a package, import by module name
                module_name = ".".join(package_parts + [script_path.stem])
                module = importlib.import_module(module_name)
            else:
                # It's a standalone script
                spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
                if spec is None or spec.loader is None:
                    raise ImportError(f"Could not load spec from {script_path}")
                module = importlib.util.module_from_spec(spec)
                sys.modules[script_path.stem] = module
                spec.loader.exec_module(module)

            # First preference: default_agent instance
            if hasattr(module, "default_agent"):
                return type(module.default_agent)
            
            # Second preference: Find class by name convention
            for name, obj in module.__dict__.items():
                if isinstance(obj, type) and name.endswith("Agent") and obj.__module__ == module.__name__:
                    return obj
                    
            raise ValueError(f"Could not find an Agent class in {script_path}")
            
        finally:
            # We don't remove root_path from sys.path because other imports might depend on it
            # during execution (e.g. tools, other modules)
            pass
