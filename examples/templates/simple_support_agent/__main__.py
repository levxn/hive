"""CLI entry point for simple_support_agent."""

import asyncio
import click

from .agent import Agent


@click.command()
@click.option("--model", "-m", default=None, help="LLM model to use")
@click.option("--tui", is_flag=True, help="Launch in TUI mode")
def main(model: str | None, tui: bool):
    """A basic customer support agent"""
    
    agent = Agent(model=model)
    
    if tui:
        # TODO: Integrate with Hive TUI
        click.echo("TUI mode not yet implemented. Use: hive run . --tui")
        return
    
    click.echo(f"Agent: {agent.graph_spec.id}")
    click.echo("Ready to execute.")


if __name__ == "__main__":
    main()