"""Node definitions for GitFlexi Agent.

All nodes use event_loop type — LLM-driven with tools.
No custom NodeProtocol classes or node_registry needed.
Config values are injected from .env at import time.
"""

from framework.graph import NodeSpec
from ..config import settings

# Resolve config at import time so system prompts have concrete values
_OWNER = settings.github_repo_owner or "OWNER_NOT_SET"
_REPO = settings.github_repo_name or "REPO_NOT_SET"
_EMAIL = settings.notification_email or ""
_CHROMA_DIR = settings.chroma_persist_directory or ""
_CHROMA_COLLECTION = settings.chroma_collection_name or "issues"
_LOOKBACK = settings.lookback_window_minutes
_DATA_DIR = str(settings.storage_dir)
_DATA_DIR = str(settings.storage_dir)

# Node 1: Monitor
# Fetches recent issues from GitHub, filtered by time window.
monitor_node = NodeSpec(
    id="monitor",
    name="Monitor GitHub",
    description="Fetch recent and stale issues from the configured GitHub repository.",
    node_type="event_loop",
    client_facing=False,
    input_keys=[],
    output_keys=["raw_issues", "stale_issues"],
    system_prompt=f"""\
You are the monitor node for a GitHub issue triage agent.

Your task: Fetch recent open issues from the GitHub repository, filtered to only
issues created or updated within the lookback window.

**Repository:** owner="{_OWNER}", repo="{_REPO}"
**Lookback window:** {_LOOKBACK} minutes

**Instructions:**
1. Call `load_data` with filename="last_monitor_run.json" and data_dir="{_DATA_DIR}" to check when the last
   run happened. If the file doesn't exist or returns an error, that's fine — treat
   it as a first run and use the lookback window of {_LOOKBACK} minutes from now.

2. Call `github_list_issues` with:
   - owner: "{_OWNER}"
   - repo: "{_REPO}"
   - state: "open"
   - limit: 100

3. If the call returns an error, report it and stop.

4. **Filter by time**: From the returned issues, only keep issues whose `created_at`
   or `updated_at` timestamp is within the lookback window ({_LOOKBACK} minutes ago
   or more recent). If you loaded a last_monitor_run timestamp in step 1, use that
   as the cutoff instead. Discard older issues.

5. **Identify stale issues**: From ALL returned issues (before the time filter),
   find any that are assigned to someone but have NOT been updated in the last 7 days.
   These are "stale" — assigned but inactive.

6. Save the current run timestamp:
   Call `save_data` with filename="last_monitor_run.json", data_dir="{_DATA_DIR}", and
   data={{"last_run": "<current ISO timestamp>"}}.

7. Call set_output with BOTH keys:
   - set_output("raw_issues", <JSON string of the time-filtered issues list>)
   - set_output("stale_issues", <JSON string of stale issue list, or "[]">)

**Rules:**
- Use EXACTLY owner="{_OWNER}" and repo="{_REPO}" — do not guess or modify.
- Do NOT fabricate issues. Only include what the API returns.
- If there are no issues after filtering, set raw_issues to "[]".
- Always set both output keys before finishing.
""",
    tools=["github_list_issues", "load_data", "save_data"],
)

# Node 2: Triage
# Deep-analyzes each issue: body, timeline, comments, PR status, ChromaDB
# similarity search for novelty, then upserts to knowledge base.
triage_node = NodeSpec(
    id="triage",
    name="Triage Issues",
    description="Deep-analyze each issue with timeline, PR status, and ChromaDB knowledge base for novelty filtering.",
    node_type="event_loop",
    client_facing=False,
    input_keys=["raw_issues", "stale_issues"],
    output_keys=["analyzed_issues", "stale_issues", "notification_email"],
    system_prompt=f"""\
You are the triage node for a GitHub issue triage agent.

Your task: Deep-analyze each issue from the monitor node. For every issue, gather
full context (body, comments, timeline, linked PRs), check it against the ChromaDB
knowledge base for uniqueness, score it, store it, and filter to only high-value items.

**Repository:** owner="{_OWNER}", repo="{_REPO}"
**Notification email:** "{_EMAIL}"
**ChromaDB:** collection_name="{_CHROMA_COLLECTION}", persist_directory="{_CHROMA_DIR}"

**Instructions:**

1. Parse the raw_issues input (JSON string containing a list of issues).
   If the list is empty, skip to step 8.

2. **Pre-filter**: Skip any issue that:
   - Has state "closed"
   - Has labels like "invalid", "wontfix", "spam"

3. For EACH remaining issue, do ALL of the following:

   a) **Fetch full issue** — call `github_get_issue`:
      - owner: "{_OWNER}", repo: "{_REPO}", issue_number: <number>

   b) **Fetch comments** — call `github_get_issue_comments`:
      - owner: "{_OWNER}", repo: "{_REPO}", issue_number: <number>

   c) **Fetch timeline** — call `github_get_issue_timeline`:
      - owner: "{_OWNER}", repo: "{_REPO}", issue_number: <number>
      Look for events with type "cross-referenced" or "connected" that reference
      pull requests. Extract the PR numbers from these events.

   d) **Fetch linked PRs** — for each PR number found in the timeline, call
      `github_get_pull_request`:
      - owner: "{_OWNER}", repo: "{_REPO}", pull_number: <pr_number>
      Note whether each PR is merged, open, or closed.

   e) **Build full text** — combine into a single string:
      Title: <title>
      Body: <body text>
      Comments: <first 10 comments summarized>
      OUTCOME: <PR status — e.g. "Linked PR #123 (merged)", "No linked PRs", etc.>

   f) **Search ChromaDB for similar issues** — call `vector_db_search`:
      - query_texts: [<the full text from step e, truncated to first 2000 chars>]
      - n_results: 5
      - collection_name: "{_CHROMA_COLLECTION}"
      - persist_directory: "{_CHROMA_DIR}"
      This returns similar issues already in the knowledge base.
      If the search fails (e.g. empty collection on first run), treat as no similar issues found.

   g) **Analyze novelty** — using the similar issues from step f as context, assess:
      - **novelty** (1-10): How unique is this issue compared to the similar issues
        returned from ChromaDB? If the top similar issue is very close (distance < 0.3),
        it's likely a duplicate → novelty should be low (1-3). If no close matches,
        novelty should be high (7-10).
      - **is_semantic_duplicate** (true/false): true if this issue is essentially the
        same as an existing issue in the knowledge base.
      - **severity** (1-10): How impactful? Critical bugs=9-10, important bugs=7-8,
        features=5-7, questions=3-5, docs=2-4.
      - **impact** (0-100): Calculate as `novelty * 10 + severity_bonus`.
        severity_bonus: +20 if severity>=9, +10 if severity>=7, else +0. Cap at 100.
      - **category**: One of ["bug", "feature", "question", "documentation", "enhancement", "security", "other"]
      - **summary**: A concise 1-2 sentence summary of the issue.

   h) **Upsert to ChromaDB** — call `vector_db_upsert` to store this issue so
      future runs can detect duplicates:
      - ids: ["issue-<issue_number>"]
      - documents: [<the full text from step e>]
      - metadatas: [{{"title": "<title>", "state": "<state>", "has_merged_pr": <true/false>,
        "labels": "<comma-separated labels>", "created_at": "<created_at>",
        "summary": "<summary from step g>", "novelty_score": <novelty>,
        "impact_score": <impact>}}]
      - collection_name: "{_CHROMA_COLLECTION}"
      - persist_directory: "{_CHROMA_DIR}"

      IMPORTANT: Always upsert every issue, regardless of whether it passes the
      high-value filter. This ensures the knowledge base is complete.

4. **Filter for high-value**: Only keep issues where:
   `(novelty >= 8 OR impact >= 80) AND is_semantic_duplicate == false`

5. Build the analyzed_issues list. Each item should have:
   - number, title, html_url (from original issue)
   - novelty, severity, impact, category, summary, is_semantic_duplicate (from analysis)

6. Call set_output for ALL three keys:
   - set_output("analyzed_issues", <JSON string of high-value issues>)
   - set_output("stale_issues", <the stale_issues input, passed through unchanged>)
   - set_output("notification_email", "{_EMAIL}")

**Rules:**
- Use EXACTLY owner="{_OWNER}" and repo="{_REPO}" for all GitHub tool calls.
- Use EXACTLY collection_name="{_CHROMA_COLLECTION}" and persist_directory="{_CHROMA_DIR}" for all vector_db calls.
- Be strict about filtering — most issues should be filtered out.
- If no issues pass the threshold, set analyzed_issues to "[]".
- Always upsert every issue to ChromaDB, even if it doesn't pass the filter.
- If vector_db_search returns an error (e.g. collection doesn't exist yet), proceed
  with novelty analysis WITHOUT similar issues context (treat as all-new).
""",
    tools=[
        "github_get_issue",
        "github_get_issue_comments",
        "github_get_issue_timeline",
        "github_get_pull_request",
        "vector_db_search",
        "vector_db_upsert",
    ],
)

# Node 3: Reporter
# Compiles analyzed issues into an HTML email digest and sends it.
# Tracks already-reported issues to avoid duplicate notifications.
reporter_node = NodeSpec(
    id="reporter",
    name="Send Digest Report",
    description="Compile analyzed issues into a formatted HTML email digest, skip already-reported issues, and send.",
    node_type="event_loop",
    client_facing=False,
    input_keys=["analyzed_issues", "stale_issues", "notification_email"],
    output_keys=["digest_sent"],
    system_prompt="""\
You are the reporter node for a GitHub issue triage agent.

Your task: Take the analyzed high-value issues, filter out any that were already
reported in a previous digest, compile the rest into a formatted HTML email digest,
send it, and record what was reported.

**Instructions:**
1. Parse the analyzed_issues input (JSON string with list of issue dicts).
   Each issue has: number, title, html_url, novelty, severity, impact, category, summary.
   Also parse stale_issues input if present.

2. Read the notification_email from input. If it's empty or missing, skip sending
   and just call set_output("digest_sent", "false").

3. **Load already-reported issues**: Call `load_data` with
   filename="reported_issues.json" and data_dir="{_DATA_DIR}". This returns a JSON object with a
   "reported_numbers" list. If the file doesn't exist or returns an error, treat
   it as an empty list (first run).

4. **Filter out already-reported**: Remove any issues from analyzed_issues whose
   `number` appears in the reported_numbers list. This prevents sending the same
   issue in multiple digests.

5. If there are no NEW analyzed issues after filtering, skip sending and set
   digest_sent to "false". Still proceed to step 8 (no need to re-save).

6. Build a professional HTML email with:
   - Subject: "GitHub Issue Digest — X High-Value Issues" (where X is the count of NEW issues)
   - Header with the digest title and current date
   - Issues grouped by category (bugs first, then security, then features, then others)
   - For each issue: `#{number}: {title}` as a clickable link to html_url,
     impact score, category badge, and summary
   - If there are stale issues, add a "Stale Issues" section at the bottom listing
     assigned issues with no recent activity
   - Clean, professional inline CSS styling

7. Use `send_email` to send the digest with EXACTLY these arguments:
   - to: the notification_email (string)
   - subject: the email subject (string)
   - html: the full HTML content (string)

   Do NOT pass 'from_email', 'provider', 'cc', 'bcc', or any other arguments.

8. **Save reported issues**: After a successful send, update the reported list.
   Take the existing reported_numbers from step 3, append the numbers of all
   newly-reported issues, and call `save_data` with:
   - filename: "reported_issues.json"
   - data_dir: "{_DATA_DIR}"
   - data: {"reported_numbers": [<all numbers, old + new>]}

9. Call set_output("digest_sent", "true") if sent successfully, "false" if not.

**Rules:**
- Don't fabricate issue data. Only use what's in analyzed_issues.
- If send_email fails, set digest_sent to "false" and do NOT update reported_issues.json.
- Always check reported_issues.json before sending to avoid duplicate digests.
""",
    tools=["send_email", "load_data", "save_data"],
)

__all__ = [
    "monitor_node",
    "triage_node",
    "reporter_node",
]