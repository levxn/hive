# Issue Triage Agent

Triage GitHub issues using LLM-powered novelty and severity analysis, maintain a vector knowledge base for deduplication, and send categorized HTML email digests to maintainers.

Converted from the standalone `maintainer_service/` into the Hive framework.

## Architecture

```
intake (client-facing) → triage → report (client-facing) → (back to intake)
```

| Node | Type | Client-Facing | Purpose |
|------|------|--------------|---------|
| **intake** | event_loop | ✅ | Greet user, collect mode (triage/stale), time range, email preference |
| **triage** | event_loop | ❌ | Fetch issues, analyze novelty/severity against vector DB, compute impact scores |
| **report** | event_loop | ✅ | Present results, build & send HTML email digest, save report |

Forever-alive graph: `report → intake` loops back so the user can run multiple operations.

## Data Flow

| Key | Source → Target | Content |
|-----|----------------|---------|
| `task_config` | intake → triage | `{mode, lookback_hours, send_email, max_pages}` |
| `triage_results` | triage → report | `{high_value_issues, stale_issues, total_analyzed, send_email}` |
| `digest_status` | report → (end) | `"sent"` or `"skipped"` |

## Modes

### Triage (default)
Fetches recent issues within a time window, filters out noise (closed, spam-labeled, PRs),
runs deep analysis on each candidate:
- Fetches comments, timeline, linked PRs
- Queries vector DB for similar past issues
- LLM analyzes novelty (1-10) and severity (Critical/High/Medium/Low)
- Computes impact score (0-100)
- Keeps high-value issues (novelty ≥ 8 OR impact ≥ 80, not duplicate)
- Also detects stale/zombie issues (assigned but inactive 14+ days)

### Stale
Quick check for assigned issues with no activity for 14+ days.

### Backfill (standalone script)
Run `python backfill.py` to index all historical issues into the ChromaDB vector
knowledge base. This is a **separate script** — not part of the agent flow.

```bash
# Backfill all issues
python backfill.py

# Only last 30 days
python backfill.py --days 30

# Limit pagination
python backfill.py --max-pages 5
```

Run this once before your first triage so the knowledge base has context for
deduplication.

## Required Environment Variables

```bash
# GitHub
GITHUB_TOKEN=ghp_...            # GitHub personal access token
GITHUB_REPO_OWNER=adenhq        # Repository owner
GITHUB_REPO_NAME=hive           # Repository name

# LLM (for the agent runtime)
OPENAI_API_KEY=sk-...           # Or any LiteLLM-compatible provider

# Email (SMTP)
SMTP_HOST=smtp.gmail.com        # SMTP server
SMTP_PORT=587                   # SMTP port (default 587)
SMTP_USERNAME=you@gmail.com     # SMTP login / from address
SMTP_PASSWORD=xxxx-xxxx-xxxx    # SMTP app password
NOTIFICATION_EMAIL=team@co.com  # Recipient for digest emails

# Optional
EMAIL_OVERRIDE_TO=dev@test.com  # Redirect all emails (for testing)
```

## Tools Used

| Tool | Node | Purpose |
|------|------|---------|
| `github_list_issues` | triage | Fetch issues with date/label filtering |
| `github_get_issue` | triage | Get single issue details |
| `github_get_issue_comments` | triage | Get discussion thread |
| `github_get_issue_timeline` | triage | Get cross-references, label changes |
| `github_get_pull_request` | triage | Check PR merge status |
| `vector_db_upsert` | triage | Store issues in knowledge base |
| `vector_db_search` | triage | Find similar past issues |
| `vector_db_count` | triage | Check knowledge base size |
| `get_current_time` | triage | Get current timestamp for `since` filter |
| `send_email` | report | Send HTML digest via SMTP |
| `save_data` | triage, report | Save intermediate data and reports |
| `serve_file_to_user` | report | Deliver clickable report link |

## Usage

```bash
# Validate agent structure
uv run python -m issue_triage_agent validate

# Show agent info
uv run python -m issue_triage_agent info

# Run with TUI (recommended)
uv run python -m issue_triage_agent tui

# Run headless
uv run python -m issue_triage_agent run

# Interactive CLI shell
uv run python -m issue_triage_agent shell

# Or via the hive CLI
hive run examples/templates/issue_triage_agent
hive tui
```

## Success Criteria

| ID | Description | Weight |
|----|-------------|--------|
| sc-fetch-issues | Correctly fetches and filters issues within time window | 0.20 |
| sc-novelty-analysis | Performs novelty/severity analysis against vector DB | 0.25 |
| sc-knowledge-base | Upserts analyzed issues into vector DB | 0.20 |
| sc-digest-delivery | Sends email digest when requested | 0.20 |
| sc-stale-detection | Identifies stale assigned issues | 0.15 |

## Constraints

- **No fabrication** (hard): Never fabricate issue data, URLs, or analysis
- **Source accuracy** (hard): All data must come from actual GitHub API responses
- **Email safety** (hard): Only send email when explicitly requested by the user
