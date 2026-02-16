"""Runtime configuration for GitFlexi Agent."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dataclasses import dataclass

from framework.config import RuntimeConfig

# Provider-agnostic LLM config — auto-detects from ~/.hive/configuration.json
default_config = RuntimeConfig()


class AgentSettings(BaseSettings):
    """Agent-specific settings loaded from environment variables."""

    # GitHub
    github_token: str | None = None
    github_repo_owner: str | None = None
    github_repo_name: str | None = None
    github_webhook_secret: str | None = None

    # Scheduler
    analysis_interval_minutes: int = 1
    lookback_window_minutes: int = 60

    # Notification / SMTP
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    notification_email: str | None = None

    # Vector DB & Storage
    storage_dir: Path = Path.home() / ".hive" / "git_flexi_agent"
    chroma_persist_directory: str | None = None
    chroma_collection_name: str = "issues"
    sqlite_db_path: str | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.chroma_persist_directory:
            self.chroma_persist_directory = str(self.storage_dir / "chroma")
        if not self.sqlite_db_path:
            self.sqlite_db_path = str(self.storage_dir / "processed_issues.db")

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env", "../../../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = AgentSettings()


@dataclass
class AgentMetadata:
    name: str = "GitFlexi Agent"
    version: str = "1.0.0"
    description: str = (
        "Monitors a GitHub repository for new issues, analyzes them for novelty, "
        "and sends email digests of important updates."
    )
    intro_message: str = (
        "GitFlexi Agent initialized. Monitoring GitHub for new issues."
    )


metadata = AgentMetadata()
