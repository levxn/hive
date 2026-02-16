"""SQLAlchemy ORM models for GitFlexi Agent state tracking."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path

Base = declarative_base()


class ReportedIssue(Base):
    """Track issues that have been sent in email digests."""

    __tablename__ = "reported_issues"

    # Composite key: repo + issue_number
    issue_id = Column(String, primary_key=True)  # Format: "owner/repo/issue_number"
    issue_number = Column(Integer, nullable=False)
    issue_title = Column(String, nullable=False)
    repository = Column(String, nullable=False)  # Format: "owner/repo"
    digest_sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    impact_score = Column(Integer, nullable=True)
    severity = Column(String, nullable=True)

    def __repr__(self):
        return f"<ReportedIssue {self.issue_id} sent_at={self.digest_sent_at}>"


class Database:
    """Handle SQLite database operations for GitFlexi Agent."""

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite file. If None, uses ~/.hive/git_flexi_agent/state.db
        """
        if db_path is None:
            db_path = Path.home() / ".hive" / "git_flexi_agent" / "state.db"
        else:
            db_path = Path(db_path)

        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Create tables
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()

    def is_issue_reported(self, owner: str, repo: str, issue_number: int) -> bool:
        """
        Check if an issue has already been reported in a digest.

        Args:
            owner: GitHub repo owner
            repo: GitHub repo name
            issue_number: Issue number

        Returns:
            True if issue was already reported, False otherwise
        """
        issue_id = f"{owner}/{repo}/{issue_number}"
        session = self.get_session()
        try:
            existing = session.query(ReportedIssue).filter(
                ReportedIssue.issue_id == issue_id
            ).first()
            return existing is not None
        finally:
            session.close()

    def mark_issue_reported(self, owner: str, repo: str, issue_number: int,
                           issue_title: str, impact_score: int | None = None,
                           severity: str | None = None) -> ReportedIssue:
        """
        Mark an issue as reported in a digest.

        Args:
            owner: GitHub repo owner
            repo: GitHub repo name
            issue_number: Issue number
            issue_title: Issue title
            impact_score: Impact score (optional)
            severity: Severity level (optional)

        Returns:
            ReportedIssue record
        """
        issue_id = f"{owner}/{repo}/{issue_number}"
        repository = f"{owner}/{repo}"

        session = self.get_session()
        try:
            # Check if already exists, update if so
            existing = session.query(ReportedIssue).filter(
                ReportedIssue.issue_id == issue_id
            ).first()

            if existing:
                existing.digest_sent_at = datetime.now(timezone.utc)
                existing.impact_score = impact_score
                existing.severity = severity
                session.commit()
                return existing

            # Create new record
            reported = ReportedIssue(
                issue_id=issue_id,
                issue_number=issue_number,
                issue_title=issue_title,
                repository=repository,
                impact_score=impact_score,
                severity=severity,
                digest_sent_at=datetime.now(timezone.utc)
            )
            session.add(reported)
            session.commit()
            return reported
        finally:
            session.close()

    def get_reported_issues(self, owner: str, repo: str) -> list[ReportedIssue]:
        """
        Get all issues reported for a repository.

        Args:
            owner: GitHub repo owner
            repo: GitHub repo name

        Returns:
            List of ReportedIssue records
        """
        repository = f"{owner}/{repo}"
        session = self.get_session()
        try:
            issues = session.query(ReportedIssue).filter(
                ReportedIssue.repository == repository
            ).all()
            return issues
        finally:
            session.close()

    def get_reported_issue_numbers(self, owner: str, repo: str) -> set[int]:
        """
        Get set of issue numbers already reported.

        Args:
            owner: GitHub repo owner
            repo: GitHub repo name

        Returns:
            Set of issue numbers
        """
        issues = self.get_reported_issues(owner, repo)
        return {issue.issue_number for issue in issues}

    def clear_reported_issues(self, owner: str, repo: str):
        """
        Clear all reported issues for a repository (for testing/reset).

        Args:
            owner: GitHub repo owner
            repo: GitHub repo name
        """
        repository = f"{owner}/{repo}"
        session = self.get_session()
        try:
            session.query(ReportedIssue).filter(
                ReportedIssue.repository == repository
            ).delete()
            session.commit()
        finally:
            session.close()


# Global database instance
_db_instance: Database | None = None


def get_db(db_path: str | Path | None = None) -> Database:
    """
    Get or create global database instance.

    Args:
        db_path: Path to SQLite file (only used on first call)

    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
