"""
Scorer implementation.

Evaluates agent outputs against expected outcomes.
"""

from typing import Any
from .schemas import Scenario, ScenarioResult

class Scorer:
    """Evaluates scenario results."""
    
    def score(self, scenario: Scenario, output: Any, error: str | None = None) -> ScenarioResult:
        """Score a single execution."""
        raise NotImplementedError

class BasicScorer(Scorer):
    """Simple Pass/Fail scorer based on success flag or exact match."""
    
    def score(
        self, 
        scenario: Scenario, 
        output: Any, 
        duration: float,
        error: str | None = None,
        iteration: int = 1
    ) -> ScenarioResult:
        if error:
            return ScenarioResult(
                scenario_id=scenario.id,
                iteration=iteration,
                status="ERROR",
                duration_seconds=duration,
                error=error,
                score=0.0
            )

        # Check for explicit success flag in output (common pattern in Hive)
        success = False
        error_msg = error
        
        if hasattr(output, "success"):
            success = output.success
            # Capture error message from output if present and failed
            if not success and hasattr(output, "error") and output.error:
                error_msg = str(output.error)
        elif isinstance(output, dict):
            success = output.get("success", True)
            if not success and "error" in output:
                error_msg = str(output["error"])
        else:
            success = True

        return ScenarioResult(
            scenario_id=scenario.id,
            iteration=iteration,
            status="PASS" if success else "FAIL",
            duration_seconds=duration,
            output=output,
            error=error_msg,
            score=1.0 if success else 0.0
        )
