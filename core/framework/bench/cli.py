"""
CLI commands for Hive Bench.
"""

import argparse
import asyncio
import json
import yaml
from pathlib import Path
from typing import Any

from .schemas import BenchmarkConfig, Scenario
from .runner import BenchmarkRunner

def load_scenarios(scenario_path: str) -> list[Scenario]:
    """Load scenarios from JSON or YAML file."""
    path = Path(scenario_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")
    
    with open(path, "r") as f:
        if path.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
            
    # Normalize list vs dict
    scenario_list = data if isinstance(data, list) else data.get("scenarios", [])
    
    return [Scenario(**s) for s in scenario_list]


async def run_bench_command(args):
    """Execute the bench command."""
    print(f"🚀 Starting Hive Bench for {args.agent_path}...")
    
    try:
        scenarios = load_scenarios(args.scenarios)
        print(f"📝 Loaded {len(scenarios)} scenarios from {args.scenarios}")
        
        config = BenchmarkConfig(
            agent_path=args.agent_path,
            scenarios=scenarios,
            parallelism=args.parallelism,
            iterations_per_scenario=args.iterations
        )
        
        runner = BenchmarkRunner(config)
        scorecard = await runner.run()
        
        # Output results
        print("\n📊 Benchmark Results")
        print("===================")
        print(f"Agent: {scorecard.agent_name}")
        print(f"Total Runs: {scorecard.total_runs}")
        print(f"Success Rate: {scorecard.success_rate:.1%} ({scorecard.success_count}/{scorecard.total_runs})")
        print(f"Avg Latency: {scorecard.avg_latency:.2f}s")
        print(f"Failures: {scorecard.failure_count}")
        print(f"Errors: {scorecard.error_count}")
        
        if scorecard.failure_count > 0 or scorecard.error_count > 0:
            print("\n❌ Failed/Errored Runs:")
            for r in scorecard.results:
                if r.status != "PASS":
                     print(f" - Scenario '{r.scenario_id}' (Iter {r.iteration}): {r.status} - {r.error or 'Failed condition'}")

        # Save report if requested
        if args.output:
            out_path = Path(args.output)
            with open(out_path, "w") as f:
                # Basic JSON dump for now
                json.dump(scorecard.__dict__, f, default=lambda o: o.__dict__, indent=2)
            print(f"\n💾 Report saved to {out_path}")

        return 0 if scorecard.success_rate == 1.0 else 1

    except Exception as e:
        print(f"\n💥 Benchmark failed: {e}")
        return 1

def bench_command_wrapper(args):
    """Wrapper to run async bench command."""
    return asyncio.run(run_bench_command(args))

def register_bench_commands(subparsers):
    """Register bench commands with the main CLI."""
    parser = subparsers.add_parser("bench", help="Run agent benchmarks")
    parser.add_argument("agent_path", help="Path to the agent directory or script")
    parser.add_argument("--scenarios", "-s", required=True, help="Path to scenarios file (JSON/YAML)")
    parser.add_argument("--parallelism", "-p", type=int, default=1, help="Number of concurrent runs")
    parser.add_argument("--iterations", "-n", type=int, default=1, help="Iterations per scenario")
    parser.add_argument("--output", "-o", help="Path to save output report")
    parser.set_defaults(func=bench_command_wrapper)
