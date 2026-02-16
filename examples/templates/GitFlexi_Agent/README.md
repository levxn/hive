# GitFlexi Agent

A generic hive-framework template ported from `maintainer_service`.

## Features
- **Monitor**: Checks GitHub for new issues (with lookback window).
- **Triage**: Analyzes issues for novelty using Vector DB.
- **Reporting**: Sends email digests for important updates.
- **Scheduling**: Runs periodically via a built-in scheduler.
- **Serving**: Exposes a "Run Now" endpoint.

## Configuration
Ensure your `.env` file (in `hive/` root or parent directories) contains:
```ini
GITHUB_TOKEN=ghp_...
GITHUB_REPO_OWNER=owner
GITHUB_REPO_NAME=repo
OPENAI_API_KEY=sk-...
# Optional
ANALYSIS_INTERVAL_MINUTES=60
LOOKBACK_WINDOW_MINUTES=65
NOTIFICATION_EMAIL=user@example.com
```

## How to Run
 
Run commands from the repository root (`hive/`).

### 1. Backfill Knowledge Base (Recommended First Run)
Populate ChromaDB with historical issues to enable effective novelty detection.
```bash
uv run python -m examples.templates.GitFlexi_Agent.scripts.backfill --days 30
```

### 2. Scheduler Mode
Runs the agent in an infinite loop, sleeping for `ANALYSIS_INTERVAL_MINUTES` between runs.
```bash
uv run python -m examples.templates.GitFlexi_Agent schedule
```

### 2. Server Mode (Endpoint)
Starts an HTTP server (default port 8000) exposing `POST /run`.
```bash
uv run python -m examples.templates.GitFlexi_Agent serve
```

Trigger it:
```bash
curl -X POST http://localhost:8000/run -d '{"lookback_minutes": 120}'
```

### 3. One-off Run
Executes the agent logic once immediately.
```bash
uv run python -m examples.templates.GitFlexi_Agent run
```
