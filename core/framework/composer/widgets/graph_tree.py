"""Graph tree visualization widget for the Composer."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode


class GraphTreeView(Vertical):
    """Displays the agent graph as a clickable tree."""

    DEFAULT_CSS = """
    GraphTreeView {
        width: 100%;
        height: 100%;
        background: $panel;
        border: round $primary;
        padding: 1;
    }
    
    GraphTreeView Tree {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nodes = []
        self.edges = []
        self.entry_node = None
        self.selected_node = None

    def compose(self) -> ComposeResult:
        """Create the tree widget."""
        yield Static("[bold cyan]Agent Graph[/bold cyan]", classes="tree-title")
        yield Tree("Nodes", id="node-tree")

    def update_graph(self, nodes: list, edges: list, entry_node: str | None = None):
        """Update the graph structure and re-render."""
        self.nodes = nodes
        self.edges = edges
        self.entry_node = entry_node
        self.render_tree()

    def render_tree(self):
        """Render the graph as a tree."""
        tree = self.query_one("#node-tree", Tree)
        tree.clear()
        
        if not self.nodes:
            tree.root.set_label("[dim]No nodes yet. Press 'N' to add.[/dim]")
            return

        tree.root.set_label("Agent Nodes")
        tree.show_root = True
        tree.root.expand()

        # Build adjacency list
        adj = {node["id"]: [] for node in self.nodes}
        for edge in self.edges:
            adj[edge["source"]].append(edge["target"])

        # Add nodes to tree
        for node in self.nodes:
            icon = "●" if node["id"] == self.selected_node else "○"
            label = f"{icon} {node['id']} - {node['name']}"
            tree_node = tree.root.add(label, data=node["id"])
            
            # Expand selected node
            if node["id"] == self.selected_node:
                tree_node.expand()

    def select_node(self, node_id: str):
        """Highlight a node as selected."""
        self.selected_node = node_id
        self.render_tree()
        
        # Post a message to notify parent
        self.post_message(self.NodeSelected(node_id))
    
    class NodeSelected(Tree.NodeSelected):
        """Message when a node is selected."""
        def __init__(self, node_id: str):
            super().__init__(None)
            self.node_id = node_id
