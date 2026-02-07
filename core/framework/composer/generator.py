"""Code generation from ComposerState to agent files."""

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .state import ComposerState


class CodeGenerator:
    """Generates agent code from composer state."""

    def __init__(self):
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, state: ComposerState, output_path: Path) -> None:
        """Generate all agent files at the output path."""
        output_path.mkdir(parents=True, exist_ok=True)
        nodes_dir = output_path / "nodes"
        nodes_dir.mkdir(exist_ok=True)

        # Prepare template context
        context = {
            "agent_name": state.agent_name,
            "agent_description": state.agent_description,
            "goal": state.goal.model_dump() if state.goal else {},
            "nodes": [node.model_dump() for node in state.nodes],
            "edges": [edge.model_dump() for edge in state.edges],
            "entry_node": state.entry_node,
            "terminal_nodes": state.terminal_nodes,
            "default_model": state.default_model,
            "max_tokens": state.max_tokens,
            "selected_tools": state.selected_tools,
            "tool_path": "../../tools",  # Relative path to tools directory
        }

        # Generate files
        self._write_template("__init__.py.j2", output_path / "__init__.py", context)
        self._write_template("__main__.py.j2", output_path / "__main__.py", context)
        self._write_template("agent.py.j2", output_path / "agent.py", context)
        self._write_template("config.py.j2", output_path / "config.py", context)
        self._write_template("nodes.py.j2", nodes_dir / "__init__.py", context)
        
        # Generate mcp_servers.json if tools are selected
        if state.selected_tools:
            self._write_template(
                "mcp_servers.json.j2",
                output_path / "mcp_servers.json",
                context
            )

    def _write_template(self, template_name: str, output_file: Path, context: dict) -> None:
        """Render and write a template to a file."""
        template = self.env.get_template(template_name)
        content = template.render(**context)
        output_file.write_text(content)
