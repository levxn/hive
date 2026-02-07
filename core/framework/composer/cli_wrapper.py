"""CLI wrapper for integrating Composer with hive run."""

import subprocess
import sys
from pathlib import Path


def run_composer_then_runtime(agent_path: Path, model: str | None = None) -> int:
    """
    Run the Composer TUI, and if it exits successfully (code 0),
    launch the Runtime TUI for the generated agent.
    
    This provides a seamless "Edit → Run" experience.
    """
    python_cmd = sys.executable
    
    # Step 1: Launch Composer
    print(f"Launching Composer for: {agent_path}")
    composer_result = subprocess.run(
        [python_cmd, "-m", "framework.composer", str(agent_path)],
        cwd=Path(__file__).parent.parent.parent,  # hive/core
    )
    
    # If Composer exited with success (0), launch Runtime
    if composer_result.returncode == 0:
        print(f"\nLaunching Runtime TUI for: {agent_path}")
        
        runtime_cmd = [python_cmd, "-m", "framework.runner.cli", "run", str(agent_path), "--tui"]
        if model:
            runtime_cmd.extend(["--model", model])
        
        runtime_result = subprocess.run(runtime_cmd, cwd=Path(__file__).parent.parent.parent)
        return runtime_result.returncode
    
    return composer_result.returncode


def should_compose(agent_path: Path) -> bool:
    """
    Check if we should launch the Composer.
    Returns True if agent doesn't exist or is incomplete.
    """
    if not agent_path.exists():
        return True
    
    # Check for required files
    required_files = ["agent.py", "config.py", "nodes/__init__.py"]
    for file in required_files:
        if not (agent_path / file).exists():
            return True
    
    return False


def prompt_user_choice() -> str:
    """Prompt user to choose between editing or running."""
    print("\nAgent exists. What would you like to do?")
    print("  [1] Edit with Composer")
    print("  [2] Run with TUI")
    print("  [3] Cancel")
    
    while True:
        choice = input("\nChoice (1/2/3): ").strip()
        if choice in ["1", "2", "3"]:
            return choice
        print("Invalid choice. Please enter 1, 2, or 3.")
