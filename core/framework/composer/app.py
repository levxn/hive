"""Main Composer TUI Application."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Static, TextArea, Tree

from .generator import CodeGenerator
from .modals import AgentInfoModal, GoalEditorModal, NodeEditorModal
from .state import ComposerState, EdgeData, GoalData, NodeData
from .widgets import GraphTreeView


class ComposerApp(App):
    """Hive Agent Composer - Interactive TUI for building agents."""

    CSS = """
    Screen {
        align: center middle;
    }
    
    #main-container {
        width: 100%;
        height: 100%;
        padding: 1;
    }
    
    #left-pane {
        width: 30%;
        height: 100%;
    }
    
    #right-pane {
        width: 70%;
        height: 100%;
        padding: 0 1;
    }
    
    .instruction {
        background: $boost;
        color: $text;
        padding: 1;
        margin-bottom: 1;
    }
    
    .field-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    
    Input, TextArea {
        margin-bottom: 1;
    }
    
    #button-row {
        dock: bottom;
        height: 3;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    #close-button {
        dock: right;
        margin: 0 1;
    }
    
    #agent-info {
        background: $boost;
        color: $text;
        padding: 0 2;
        text-align: center;
    }
    """

    
    BINDINGS = [
        Binding("escape", "quit", "Quit (ESC)", show=True, priority=False),
        Binding("ctrl+c", "quit", show=False),
        Binding("n", "new_node", "New Node"),
        Binding("e", "edit_node", "Edit Node"),
        Binding("d", "delete_node", "Delete Node"),
        Binding("o", "edit_goal", "Edit Goal"),
        Binding("g", "generate", "Generate"),
    ]

    def action_quit(self) -> None:
        """Quit the app, but only if no input is focused."""
        focused = self.focused
        if isinstance(focused, (Input, TextArea)):
            # If an input is focused, unfocus it instead of quitting
            self.set_focus(None)
        else:
            # No input focused, safe to quit
            self.exit()

    def __init__(self, agent_path: Path | None = None):
        super().__init__()
        self.state = ComposerState()
        self.agent_path = agent_path
        self.generator = CodeGenerator()
        
        # If agent_path exists, load existing agent
        if agent_path and agent_path.exists():
            self._load_existing_agent(agent_path)

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()
        
        # Add close button to header
        yield Button("✕ Close", variant="error", id="close-button")
        
        # Show agent info if set
        if self.state.agent_name:
            yield Static(
                f"[bold]{self.state.agent_name}[/bold] - {self.state.agent_description}",
                id="agent-info"
            )
        
        with Container(id="main-container"):
            with Horizontal():
                # Left pane: Graph tree
                with Vertical(id="left-pane"):
                    yield GraphTreeView()
                
                # Right pane: Node editor
                with Vertical(id="right-pane"):
                    yield Static(
                        "[bold cyan]Composer Shortcuts[/bold cyan]\n\n"
                        "[bold]N[/bold] - Add New Node\n"
                        "[bold]E[/bold] - Edit Selected Node\n"
                        "[bold]D[/bold] - Delete Selected Node\n"
                        "[bold]O[/bold] - Edit Goal\n"
                        "[bold]G[/bold] - Generate Agent\n"
                        "[bold]ESC[/bold] - Unfocus/Quit\n",
                        id="instructions"
                    )
                    
                    # Node details (shown when node selected)
                    yield Label("", id="node-details")
        
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the composer on mount."""
        # If agent not set, show initial modal
        if not self.state.agent_name:
            self.show_agent_info_modal()
        else:
            self._update_graph_view()
    
    def show_agent_info_modal(self) -> None:
        """Show agent info modal when starting."""
        def check_result(result):
            if result:
                self.state.agent_name = result["name"]
                self.state.agent_description = result["description"]
                self._update_agent_info()
                self._update_graph_view()
            else:
                # User cancelled, exit
                self.exit()

        self.push_screen(AgentInfoModal(), check_result)
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "agent-name":
            self.state.agent_name = event.value
        elif event.input.id == "agent-description":
            self.state.agent_description = event.value

    def on_key(self, event) -> None:
        """Handle key events for focus management."""
        # ESC key unfocuses any focused input
        if event.key == "escape":
            focused = self.focused
            if isinstance(focused, (Input, TextArea)):
                self.set_focus(None)
                event.stop()  # Prevent quit action when unfocusing
                return

    def on_click(self, event) -> None:
        """Handle clicks to unfocus inputs when clicking outside."""
        # If clicking on a container or static element, unfocus inputs
        if isinstance(event.widget, (Container, Vertical, Horizontal, Static, Label)):
            focused = self.focused
            if isinstance(focused, (Input, TextArea)):
                self.set_focus(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "close-button":
            self.action_quit()
    
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle node selection in the tree."""
        if event.node.data:
            node_id = event.node.data
            # Update selection in tree
            tree = self.query_one(GraphTreeView)
            tree.select_node(node_id)
            
            # Find and show the node
            node = next((n for n in self.state.nodes if n.id == node_id), None)
            if node:
                self._show_node_details(node)

    def _load_existing_agent(self, agent_path: Path) -> None:
        """Load an existing agent for editing."""
        # TODO: Implement agent loading from existing files
        pass
    
    def _update_agent_info(self) -> None:
        """Update the agent info display in header."""
        try:
            info = self.query_one("#agent-info", Static)
            info.update(f"[bold]{self.state.agent_name}[/bold] - {self.state.agent_description}")
        except:
            pass  # Not mounted yet

    def _update_graph_view(self) -> None:
        """Update the graph tree visualization."""
        tree = self.query_one(GraphTreeView)
        tree.update_graph(
            nodes=[node.model_dump() for node in self.state.nodes],
            edges=[edge.model_dump() for edge in self.state.edges],
            entry_node=self.state.entry_node,
        )
    
    def _show_node_details(self, node: NodeData) -> None:
        """Show node details in the right pane."""
        details = self.query_one("#node-details", Label)
        
        tools_info = f"{len(node.tools)} tools" if node.tools else "No tools"
        
        details.update(
            f"\n[bold cyan]Selected: {node.name}[/bold cyan]\n\n"
            f"[bold]ID:[/bold] {node.id}\n"
            f"[bold]Description:[/bold] {node.description or 'N/A'}\n"
            f"[bold]Tools:[/bold] {tools_info}\n\n"
            f"[bold]System Prompt:[/bold]\n{node.system_prompt[:200]}...\n\n"
            f"Press [bold]E[/bold] to edit this node."
        )

    def action_new_node(self) -> None:
        """Add a new node to the graph."""
        def handle_result(result):
            if result:
                # Check for duplicate ID
                if any(n.id == result.id for n in self.state.nodes):
                    self.notify(f"Node with ID '{result.id}' already exists!", severity="error")
                    return
                
                self.state.nodes.append(result)
                
                # Set entry node if first
                if len(self.state.nodes) == 1:
                    self.state.entry_node = result.id
                    self.state.terminal_nodes = [result.id]
                
                self._update_graph_view()
                self.notify(f"✓ Added node: {result.id}")
        
        self.push_screen(NodeEditorModal(), handle_result)

    def action_edit_node(self) -> None:
        """Edit the selected node."""
        tree = self.query_one(GraphTreeView)
        if not tree.selected_node:
            self.notify("Select a node first", severity="warning")
            return
        
        # Find the node
        node = next((n for n in self.state.nodes if n.id == tree.selected_node), None)
        if not node:
            return
        
        def handle_result(result):
            if result:
                # Update the node in place
                idx = self.state.nodes.index(node)
                self.state.nodes[idx] = result
                
                self._update_graph_view()
                self._show_node_details(result)
                self.notify(f"✓ Updated node: {result.id}")
        
        self.push_screen(NodeEditorModal(node), handle_result)

    def action_delete_node(self) -> None:
        """Delete the selected node."""
        tree = self.query_one(GraphTreeView)
        if not tree.selected_node:
            self.notify("Select a node first", severity="warning")
            return
        
        # Remove node and its edges
        self.state.nodes = [n for n in self.state.nodes if n.id != tree.selected_node]
        self.state.edges = [
            e for e in self.state.edges 
            if e.source != tree.selected_node and e.target != tree.selected_node
        ]
        
        # Clear selection display
        details = self.query_one("#node-details", Label)
        details.update("")
        
        self._update_graph_view()
        self.notify(f"✓ Deleted node: {tree.selected_node}")

    def action_edit_goal(self) -> None:
        """Edit the agent goal."""
        def handle_result(result):
            if result:
                self.state.goal = result
                self.notify(f"✓ Goal updated: {result.name}")
        
        self.push_screen(GoalEditorModal(self.state.goal), handle_result)

    def action_generate(self) -> None:
        """Generate the agent code."""
        # Validate state
        if not self.state.agent_name:
            self.notify("Missing: Agent name", severity="error")
            return
        
        if not self.state.nodes:
            self.notify("Missing: At least one node required", severity="error")
            return
        
        if not self.state.goal:
            self.notify("Missing: Agent goal (Press O to edit goal)", severity="error")
            return
        
        if not self.state.entry_node:
            self.notify("Missing: Entry node not set", severity="error")
            return
        
        from pathlib import Path
        output_path = self.agent_path or Path.cwd() / "hive" / "examples" / "templates" / self.state.agent_name
        
        try:
            self.generator.generate(self.state, output_path)
            self.notify(f"✓ Agent generated at {output_path}", severity="information")
            self.exit(return_code=0)
        except Exception as e:
            self.notify(f"Error generating agent: {e}", severity="error")

    def _load_existing_agent(self, agent_path: Path) -> None:
        """Load an existing agent for editing."""
        # TODO: Implement agent loading from existing files
        pass

    def _update_graph_view(self) -> None:
        """Update the graph tree visualization."""
        tree = self.query_one(GraphTreeView)
        tree.update_graph(
            nodes=[node.model_dump() for node in self.state.nodes],
            edges=[edge.model_dump() for edge in self.state.edges],
            entry_node=self.state.entry_node,
        )
