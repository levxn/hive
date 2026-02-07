#!/usr/bin/env python3
"""Test script to create a simple agent end-to-end."""

import sys
from pathlib import Path

# Add hive/core to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from framework.composer.state import ComposerState, GoalData, NodeData, EdgeData
from framework.composer.generator import CodeGenerator


def main():
    """Create a simple test agent."""
    print("Creating a simple support agent...")
    
    # Create state
    state = ComposerState()
    state.agent_name = "simple_support_agent"
    state.agent_description = "A basic customer support agent"
    state.default_model = "gpt-4o-mini"
    
    # Define goal
    state.goal = GoalData(
        id="support_goal",
        name="Customer Support Goal",
        description="Provide helpful responses to customer inquiries",
        success_criteria=["response_quality", "resolution_speed"]
    )
    
    # Add nodes
    intake_node = NodeData(
        id="intake",
        name="Customer Intake",
        description="Gather customer inquiry details",
        system_prompt="You are a helpful customer support agent. Gather information about the customer's issue.",
        tools=[]
    )
    
    response_node = NodeData(
        id="response",
        name="Response Generator",
        description="Generate helpful response",
        system_prompt="You are a helpful customer support agent. Provide a clear, helpful response to the customer.",
        tools=[]
    )
    
    state.nodes = [intake_node, response_node]
    state.entry_node = "intake"
    state.terminal_nodes = ["response"]
    
    # Add edge
    state.edges = [
        EdgeData(source="intake", target="response")
    ]
    
    # Generate code
    output_path = Path(__file__).parent.parent.parent.parent / "examples" / "templates" / state.agent_name
    
    print(f"Generating agent at: {output_path}")
    
    generator = CodeGenerator()
    generator.generate(state, output_path)
    
    print("✓ Agent generated successfully!")
    print(f"\nGenerated files:")
    for file in output_path.rglob("*.py"):
        print(f"  - {file.relative_to(output_path.parent)}")
    
    print(f"\nYou can now run: hive run {output_path}")


if __name__ == "__main__":
    main()
