"""Modal dialogs for the Composer."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

from .state import NodeData, GoalData


class AgentInfoModal(ModalScreen):
    """Initial modal to collect agent name and description."""
    
    CSS = """
    AgentInfoModal {
        align: center middle;
    }
    
    #dialog {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    #button-row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Static("[bold cyan]🚀 Create New Agent[/bold cyan]\n", classes="title")
            yield Static("Let's start by giving your agent a name and description.\n")
            
            yield Label("Agent Name:")
            yield Input(placeholder="e.g., customer_support_agent", id="agent-name")
            
            yield Label("\nAgent Description:")
            yield TextArea("", id="agent-description")
            yield Static("[dim]Brief description of what this agent does[/dim]\n")
            
            with Container(id="button-row"):
                yield Button("Create Agent", variant="primary", id="create")
                yield Button("Cancel", variant="default", id="cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            name = self.query_one("#agent-name", Input).value
            desc = self.query_one("#agent-description", TextArea).text
            
            if not name:
                self.app.notify("Please enter an agent name", severity="error")
                return
            
            self.dismiss({"name": name, "description": desc})
        else:
            self.dismiss(None)


class NodeEditorModal(ModalScreen):
    """Modal for editing node properties."""
    
    CSS = """
    NodeEditorModal {
        align: center middle;
    }
    
    #dialog {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    Label {
        margin-top: 1;
    }
    
    TextArea {
        height: 8;
        margin-bottom: 1;
    }
    
    #button-row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    def __init__(self, node: NodeData | None = None):
        super().__init__()
        self.node = node or NodeData(id="", name="", system_prompt="")
    
    def compose(self) -> ComposeResult:
        title = "Edit Node" if self.node.id else "New Node"
        
        with Container(id="dialog"):
            yield Static(f"[bold cyan]✏️  {title}[/bold cyan]\n", classes="title")
            
            yield Label("Node ID:")
            yield Input(
                placeholder="e.g., intake, analysis, response",
                value=self.node.id,
                id="node-id",
                disabled=bool(self.node.id)  # Can't change ID of existing node
            )
            
            yield Label("Node Name:")
            yield Input(
                placeholder="e.g., Customer Intake, Data Analysis",
                value=self.node.name,
                id="node-name"
            )
            
            yield Label("System Prompt:")
            yield TextArea(
                self.node.system_prompt or "You are a helpful assistant.",
                id="system-prompt"
            )
            yield Static("[dim]Instructions for this node's behavior[/dim]\n")
            
            yield Label("Description (optional):")
            yield Input(
                placeholder="Brief description of this node's purpose",
                value=self.node.description or "",
                id="node-description"
            )
            
            with Container(id="button-row"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            node_id = self.query_one("#node-id", Input).value
            name = self.query_one("#node-name", Input).value
            prompt = self.query_one("#system-prompt", TextArea).text
            desc = self.query_one("#node-description", Input).value
            
            if not node_id or not name:
                self.app.notify("Please fill in ID and Name", severity="error")
                return
            
            # Create updated node
            updated_node = NodeData(
                id=node_id,
                name=name,
                system_prompt=prompt,
                description=desc or None,
                tools=self.node.tools  # Preserve existing tools
            )
            
            self.dismiss(updated_node)
        else:
            self.dismiss(None)


class GoalEditorModal(ModalScreen):
    """Modal for editing goal and success criteria."""
    
    CSS = """
    GoalEditorModal {
        align: center middle;
    }
    
    #dialog {
        width: 80;
        height: auto;
        max-height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    
    Label {
        margin-top: 1;
    }
    
    TextArea {
        height: 6;
        margin-bottom: 1;
    }
    
    #button-row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    def __init__(self, goal: GoalData | None = None):
        super().__init__()
        self.goal = goal
    
    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Static("[bold cyan]🎯 Define Agent Goal[/bold cyan]\n", classes="title")
            yield Static("What is this agent trying to achieve?\n")
            
            yield Label("Goal Name:")
            yield Input(
                placeholder="e.g., Customer Support Goal",
                value=self.goal.name if self.goal else "",
                id="goal-name"
            )
            
            yield Label("Goal Description:")
            yield TextArea(
                self.goal.description if self.goal else "",
                id="goal-description"
            )
            
            yield Label("Success Criteria (comma-separated):")
            yield Input(
                placeholder="e.g., response_quality, resolution_speed",
                value=", ".join(self.goal.success_criteria) if self.goal else "",
                id="success-criteria"
            )
            yield Static("[dim]How will you measure success?[/dim]\n")
            
            with Container(id="button-row"):
                yield Button("Save Goal", variant="primary", id="save")
                yield Button("Cancel", variant="default", id="cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            name = self.query_one("#goal-name", Input).value
            desc = self.query_one("#goal-description", TextArea).text
            criteria = self.query_one("#success-criteria", Input).value
            
            if not name:
                self.app.notify("Please enter a goal name", severity="error")
                return
            
            # Parse success criteria
            criteria_list = [c.strip() for c in criteria.split(",") if c.strip()]
            
            goal = GoalData(
                id=name.lower().replace(" ", "_"),
                name=name,
                description=desc,
                success_criteria=criteria_list
            )
            
            self.dismiss(goal)
        else:
            self.dismiss(None)
