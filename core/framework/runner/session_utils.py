"""Session utilities for CLI and runtime helpers."""

from pathlib import Path

from framework.storage.checkpoint_store import CheckpointStore
from framework.storage.session_store import SessionStore


def resolve_storage_path(agent_path: Path) -> Path:
    """Resolve the default storage path for an agent."""
    home = Path.home()
    return home / ".hive" / "agents" / agent_path.name


def load_session_store(agent_path: Path) -> SessionStore:
    """Create a SessionStore for an agent."""
    storage_path = resolve_storage_path(agent_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    return SessionStore(storage_path)


def load_checkpoint_store(agent_path: Path) -> CheckpointStore:
    """Create a CheckpointStore for an agent."""
    storage_path = resolve_storage_path(agent_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    return CheckpointStore(storage_path)
