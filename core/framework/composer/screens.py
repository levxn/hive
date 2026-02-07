"""Wizard screens for step-by-step agent composition."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static, TextArea


class AgentInfoScreen(Screen):
    """Step 1: Collect basic agent information."""

    CSS = """
    AgentInfoScreen {
        align: center middle;
    }
    
    #info-container {
        width: 80;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 2;
    }
    
    .field-label {
        margin-top: 1;
        margin-bottom: 0;
        color: $text;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Container(id="info-container"):
            yield Static(
                "[bold cyan]Step 1: Agent Information[/bold cyan]\n\n"
                "Let's start by giving your agent a name and description.\n\n"
                "[dim][bold]✕ Press [bold]ESC[/bold]",
                classes="instruction"
            )
            
            yield Label("Agent Name:", classes="field-label")
            yield Input(
                placeholder="e.g., customer_support_agent",
                value=self.state.agent_name,
                id="agent-name"
            )
            
            yield Label("Description:", classes="field-label")
            yield Input(
                placeholder="e.g., Handles customer inquiries and support tickets",
                value=self.state.agent_description,
                id="agent-description"
            )
            
            with Container(id="button-row"):
                yield Button("Next →", variant="primary", id="next")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            # Save values
            name_input = self.query_one("#agent-name", Input)
            desc_input = self.query_one("#agent-description", Input)
            
            if not name_input.value.strip():
                self.notify("Please enter an agent name", severity="error")
                return
            
            self.state.agent_name = name_input.value.strip()
            self.state.agent_description = desc_input.value.strip()
            
            # Go to next screen
            self.app.push_screen(GoalDefinitionScreen(self.state))
        elif event.button.id == "cancel":
            self.app.pop_screen()


class GoalDefinitionScreen(Screen):
    """Step 2: Define the agent's goal."""

    CSS = """
    GoalDefinitionScreen {
        align: center middle;
    }
    
    #goal-container {
        width: 80;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 2;
    }
    
    .field-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    
    Input, TextArea {
        margin-bottom: 1;
    }
    
    TextArea {
        height: 5;
    }
    
    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Container(id="goal-container"):
            yield Static(
                "[bold cyan]Step 2: Goal Definition[/bold cyan]\n\n"
                "Define what your agent aims to achieve.",
                classes="instruction"
            )
            
            yield Label("Goal Name:", classes="field-label")
            yield Input(
                placeholder="e.g., customer_support_goal",
                value=self.state.goal.id if self.state.goal else "",
                id="goal-id"
            )
            
            yield Label("Goal Description:", classes="field-label")
            yield TextArea(
                text=self.state.goal.description if self.state.goal else "",
                id="goal-description"
            )
            
            yield Label("Success Criteria (comma-separated):", classes="field-label")
            yield Input(
                placeholder="e.g., response_quality, resolution_time",
                value=", ".join(self.state.goal.success_criteria) if self.state.goal else "",
                id="success-criteria"
            )
            
            with Container(id="button-row"):
                yield Button("← Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            from ..state import GoalData
            
            goal_id = self.query_one("#goal-id", Input).value.strip()
            goal_desc = self.query_one("#goal-description", TextArea).text.strip()
            criteria_text = self.query_one("#success-criteria", Input).value.strip()
            
            if not goal_id:
                self.notify("Please enter a goal ID", severity="error")
                return
            
            criteria = [c.strip() for c in criteria_text.split(",") if c.strip()]
            
            self.state.goal = GoalData(
                id=goal_id,
                name=goal_id.replace("_", " ").title(),
                description=goal_desc,
                success_criteria=criteria
            )
            
            self.app.push_screen(NodeEditorScreen(self.state))
        elif event.button.id == "back":
            self.app.pop_screen()


class NodeEditorScreen(Screen):
    """Step 3: Add and edit nodes."""

    CSS = """
    NodeEditorScreen {
        align: center middle;
    }
    
    #node-container {
        width: 90;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 2;
    }
    
    .field-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    
    Input, TextArea {
        margin-bottom: 1;
    }
    
    TextArea {
        height: 8;
    }
    
    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    .node-list {
        margin: 1 0;
        padding: 1;
        background: $surface;
        height: 10;
        overflow-y: scroll;
    }
    """

    def __init__(self, state):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Container(id="node-container"):
            yield Static(
                "[bold cyan]Step 3: Node Editor[/bold cyan]\n\n"
                "Add nodes to your agent. Each node represents a processing step.",
                classes="instruction"
            )
            
            # Node list
            node_list = "\n".join(
                f"  • {node.id} - {node.name}" for node in self.state.nodes
            ) if self.state.nodes else "  [dim]No nodes yet[/dim]"
            
            yield Static(f"Current Nodes:\n{node_list}", classes="node-list")
            
            yield Label("Node ID:", classes="field-label")
            yield Input(placeholder="e.g., intake", id="node-id")
            
            yield Label("Node Name:", classes="field-label")
            yield Input(placeholder="e.g., Customer Intake", id="node-name")
            
            yield Label("System Prompt:", classes="field-label")
            yield TextArea(
                text="You are a helpful assistant.",
                id="system-prompt"
            )
            
            yield Label("Tools (comma-separated):", classes="field-label")
            yield Input(
                placeholder="e.g., web_search, send_email",
                id="tools"
            )
            
            with Container(id="button-row"):
                yield Button("Add Node", variant="success", id="add-node")
                yield Button("← Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-node":
            from ..state import NodeData
            
            node_id = self.query_one("#node-id", Input).value.strip()
            node_name = self.query_one("#node-name", Input).value.strip()
            prompt = self.query_one("#system-prompt", TextArea).text.strip()
            tools_text = self.query_one("#tools", Input).value.strip()
            
            if not node_id:
                self.notify("Please enter a node ID", severity="error")
                return
            
            # Check for duplicates
            if any(n.id == node_id for n in self.state.nodes):
                self.notify(f"Node '{node_id}' already exists", severity="error")
                return
            
            tools = [t.strip() for t in tools_text.split(",") if t.strip()]
            
            node = NodeData(
                id=node_id,
                name=node_name or node_id.replace("_", " ").title(),
                system_prompt=prompt,
                tools=tools
            )
            
            self.state.nodes.append(node)
            
            # Set entry node if this is the first
            if len(self.state.nodes) == 1:
                self.state.entry_node = node_id
            
            self.notify(f"✓ Added node: {node_id}")
            
            # Clear inputs for next node
            self.query_one("#node-id", Input).value = ""
            self.query_one("#node-name", Input).value = ""
            self.query_one("#tools", Input).value = ""
            
            # Refresh the screen
            self.refresh()
            
        elif event.button.id == "next":
            if not self.state.nodes:
                self.notify("Please add at least one node", severity="error")
                return
            
            self.app.push_screen(EdgeWiringScreen(self.state))
            
        elif event.button.id == "back":
            self.app.pop_screen()


class EdgeWiringScreen(Screen):
    """Step 4: Wire nodes together."""

    CSS = """
    EdgeWiringScreen {
        align: center middle;
    }
    
    #edge-container {
        width: 80;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 2;
    }
    
    .field-label {
        margin-top: 1;
        margin-bottom: 0;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    .edge-list {
        margin: 1 0;
        padding: 1;
        background: $surface;
        height: 10;
        overflow-y: scroll;
    }
    """

    def __init__(self, state):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Container(id="edge-container"):
            yield Static(
                "[bold cyan]Step 4: Edge Wiring[/bold cyan]\n\n"
                "Connect your nodes to define the agent's flow.",
                classes="instruction"
            )
            
            # Available nodes
            nodes_text = ", ".join(node.id for node in self.state.nodes)
            yield Static(f"Available nodes: {nodes_text}\n", classes="field-label")
            
            # Edge list
            edge_list = "\n".join(
                f"  • {edge.source} → {edge.target}" for edge in self.state.edges
            ) if self.state.edges else "  [dim]No edges yet[/dim]"
            
            yield Static(f"Current Edges:\n{edge_list}", classes="edge-list")
            
            yield Label("Source Node:", classes="field-label")
            yield Input(placeholder="Node ID", id="source")
            
            yield Label("Target Node:", classes="field-label")
            yield Input(placeholder="Node ID", id="target")
            
            with Container(id="button-row"):
                yield Button("Add Edge", variant="success", id="add-edge")
                yield Button("← Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-edge":
            from ..state import EdgeData
            
            source = self.query_one("#source", Input).value.strip()
            target = self.query_one("#target", Input).value.strip()
            
            if not source or not target:
                self.notify("Please enter both source and target", severity="error")
                return
            
            # Validate nodes exist
            node_ids = [n.id for n in self.state.nodes]
            if source not in node_ids:
                self.notify(f"Source node '{source}' not found", severity="error")
                return
            if target not in node_ids:
                self.notify(f"Target node '{target}' not found", severity="error")
                return
            
            edge = EdgeData(source=source, target=target)
            self.state.edges.append(edge)
            
            self.notify(f"✓ Added edge: {source} → {target}")
            
            # Clear inputs
            self.query_one("#source", Input).value = ""
            self.query_one("#target", Input).value = ""
            
            self.refresh()
            
        elif event.button.id == "next":
            self.app.push_screen(ReviewScreen(self.state))
            
        elif event.button.id == "back":
            self.app.pop_screen()


class ReviewScreen(Screen):
    """Step 5: Review and generate."""

    CSS = """
    ReviewScreen {
        align: center middle;
    }
    
    #review-container {
        width: 80;
        height: auto;
        background: $panel;
        border: thick $primary;
        padding: 2;
    }
    
    .review-content {
        margin: 1 0;
        padding: 1;
        background: $surface;
        height: 20;
        overflow-y: scroll;
    }
    
    #button-row {
        margin-top: 2;
        height: 3;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        with Container(id="review-container"):
            yield Static(
                "[bold cyan]Step 5: Review & Generate[/bold cyan]\n\n"
                "Review your agent configuration and generate the code.",
                classes="instruction"
            )
            
            # Build review text
            review_text = f"""[bold]Agent:[/bold] {self.state.agent_name}
[bold]Description:[/bold] {self.state.agent_description}

[bold]Goal:[/bold] {self.state.goal.name if self.state.goal else 'N/A'}
{self.state.goal.description if self.state.goal else ''}

[bold]Nodes ({len(self.state.nodes)}):[/bold]
"""
            for node in self.state.nodes:
                review_text += f"  • {node.id} - {node.name}\n"
                if node.tools:
                    review_text += f"    Tools: {', '.join(node.tools)}\n"
            
            review_text += f"\n[bold]Edges ({len(self.state.edges)}):[/bold]\n"
            for edge in self.state.edges:
                review_text += f"  • {edge.source} → {edge.target}\n"
            
            review_text += f"\n[bold]Entry Node:[/bold] {self.state.entry_node}\n"
            
            yield Static(review_text, classes="review-content")
            
            with Container(id="button-row"):
                yield Button("← Back", variant="default", id="back")
                yield Button("Generate!", variant="success", id="generate")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate":
            from pathlib import Path
            from ..generator import CodeGenerator
            
            if not self.state.is_complete():
                self.notify("Agent configuration incomplete!", severity="error")
                return
            
            # Generate code
            output_path = Path.cwd() / "hive" / "examples" / "templates" / self.state.agent_name
            generator = CodeGenerator()
            
            try:
                generator.generate(self.state, output_path)
                self.notify(f"✓ Agent generated at {output_path}!", severity="information")
                
                # Exit with success code
                self.app.exit(0)
                
            except Exception as e:
                self.notify(f"Error: {e}", severity="error")
                
        elif event.button.id == "back":
            self.app.pop_screen()
