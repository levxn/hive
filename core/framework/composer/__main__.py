#!/usr/bin/env python3
"""CLI entry point for the Composer."""

import sys
from pathlib import Path


def main():
    """Run the Composer TUI."""
    from framework.composer import ComposerApp
    
    # Check if an agent path was provided
    agent_path = None
    if len(sys.argv) > 1:
        agent_path = Path(sys.argv[1])
    
    app = ComposerApp(agent_path=agent_path)
    exit_code = app.run()
    
    # Exit code 0 means "generate and run"
    # We'll handle the transition in the wrapper script
    sys.exit(exit_code if exit_code else 0)


if __name__ == "__main__":
    main()
