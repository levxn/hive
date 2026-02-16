#!/usr/bin/env python3
"""Standalone backfill script — populate ChromaDB knowledge base with GitHub issues.

Run this BEFORE your first agent triage so the knowledge base has context
for novelty/deduplication analysis.

Usage:
    python backfill.py                     # backfill ALL issues
    python backfill.py --days 30           # only issues from last 30 days
    python backfill.py --max-pages 5       # limit pagination
    python backfill.py --collection issues # custom collection name

Requires:
    - .env file in the same directory with GITHUB_TOKEN, GITHUB_REPO_OWNER, etc.
    - aden_tools package (available at ../../../tools/src)
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

_agent_dir = Path(__file__).parent.resolve()
_env_path = _agent_dir / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# Resolve relative CHROMA_PERSIST_DIR to absolute (relative to agent dir)
_chroma_dir = os.environ.get("CHROMA_PERSIST_DIR", "")
if _chroma_dir and not os.path.isabs(_chroma_dir):
    os.environ["CHROMA_PERSIST_DIR"] = str(_agent_dir / _chroma_dir)

# Add aden_tools to path
_tools_path = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "src"
if str(_tools_path) not in sys.path:
    sys.path.insert(0, str(_tools_path))

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Register MCP tools
# ---------------------------------------------------------------------------
mcp = FastMCP("backfill")

from aden_tools.tools.github_tool import register_tools as register_github_tools
from aden_tools.tools.vector_db_tool import register_tools as register_vector_db_tools

register_github_tools(mcp, credentials=None)
register_vector_db_tools(mcp)

_tools = mcp._tool_manager._tools


def call_tool(name: str, **kwargs):
    """Call a registered MCP tool and return the result."""
    if name not in _tools:
        raise ValueError(f"Tool '{name}' not registered. Available: {list(_tools.keys())}")
    return _tools[name].fn(**kwargs)


def unwrap(response):
    """Extract 'data' from the standard aden_tools response format."""
    if isinstance(response, dict):
        if "error" in response:
            return None
        if "success" in response and "data" in response:
            return response["data"]
    return response


# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------
OWNER = os.getenv("GITHUB_REPO_OWNER", "adenhq")
REPO = os.getenv("GITHUB_REPO_NAME", "hive")
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION_NAME", "issue_knowledge_base")


def backfill(days: int | None = None, max_pages: int = 20, collection: str | None = None):
    """Fetch GitHub issues and upsert them into ChromaDB.

    Args:
        days: Only index issues created within the last N days. None = all.
        max_pages: Maximum number of 100-issue pages to fetch.
        collection: ChromaDB collection name override.
    """
    col = collection or CHROMA_COLLECTION
    since_dt = None
    if days:
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        print(f"Backfilling issues since {since_dt.isoformat()} ({days} day(s))")
    else:
        print("Backfilling ALL issues (no date filter)")

    print(f"  Repo:       {OWNER}/{REPO}")
    print(f"  Collection: {col}")
    print(f"  ChromaDB:   {CHROMA_DIR}")
    print(f"  Max pages:  {max_pages}")
    print()

    total_indexed = 0
    total_skipped = 0
    page = 1

    while page <= max_pages:
        print(f"--- Page {page} ---")
        resp = call_tool(
            "github_list_issues",
            owner=OWNER,
            repo=REPO,
            state="all",
            sort="created",
            direction="desc",
            limit=100,
            page=page,
        )
        issues = unwrap(resp)
        if not issues:
            print("  No more issues returned. Done.")
            break

        # Filter
        batch_ids = []
        batch_docs = []
        batch_metas = []

        for issue in issues:
            # Skip PRs
            if "pull_request" in issue:
                total_skipped += 1
                continue

            # Date filter
            created_at = issue.get("created_at", "")
            if since_dt and created_at:
                try:
                    issue_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if issue_dt < since_dt:
                        total_skipped += 1
                        continue
                except (ValueError, TypeError):
                    pass

            number = str(issue.get("number", ""))
            title = issue.get("title", "")
            body = issue.get("body") or "No description provided."
            state = issue.get("state", "unknown")
            labels_raw = issue.get("labels", [])
            labels = ", ".join(
                lbl["name"] if isinstance(lbl, dict) else str(lbl) for lbl in labels_raw
            )

            # Build document text
            doc_text = f"{title}\n\n{body}"

            # Build a short summary from title (lightweight — no LLM call needed)
            summary = title

            batch_ids.append(number)
            batch_docs.append(doc_text)
            batch_metas.append({
                "title": title,
                "state": state,
                "labels": labels,
                "created_at": created_at,
                "summary": summary,
            })

            # Flush in batches of 10
            if len(batch_ids) >= 10:
                _upsert_batch(batch_ids, batch_docs, batch_metas, col)
                total_indexed += len(batch_ids)
                batch_ids, batch_docs, batch_metas = [], [], []

        # Flush remaining
        if batch_ids:
            _upsert_batch(batch_ids, batch_docs, batch_metas, col)
            total_indexed += len(batch_ids)

        # Progress
        count_resp = call_tool(
            "vector_db_count",
            collection_name=col,
            persist_directory=CHROMA_DIR,
        )
        db_count = unwrap(count_resp) if unwrap(count_resp) else count_resp
        print(f"  Page {page} done. Indexed {total_indexed} total. "
              f"Skipped {total_skipped}. KB size: {db_count}")

        # Last page if fewer than 100 results
        if len(issues) < 100:
            print("  Less than 100 results — last page.")
            break

        page += 1
        time.sleep(0.5)  # gentle rate limiting

    print()
    print(f"=== Backfill complete ===")
    print(f"  Total indexed:  {total_indexed}")
    print(f"  Total skipped:  {total_skipped}")
    print(f"  Pages fetched:  {page}")


def _upsert_batch(ids, docs, metas, collection):
    """Upsert a batch of documents into ChromaDB."""
    try:
        call_tool(
            "vector_db_upsert",
            ids=ids,
            documents=docs,
            metadatas=metas,
            collection_name=collection,
            persist_directory=CHROMA_DIR,
        )
    except Exception as e:
        print(f"  WARNING: upsert failed for batch {ids}: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Backfill ChromaDB knowledge base with GitHub issues."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only index issues from the last N days (default: all)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum number of 100-issue pages to fetch (default: 20)",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help=f"ChromaDB collection name (default: {CHROMA_COLLECTION})",
    )
    args = parser.parse_args()
    backfill(days=args.days, max_pages=args.max_pages, collection=args.collection)


if __name__ == "__main__":
    main()
