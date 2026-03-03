"""Node definitions for Issue Triage Agent.

Architecture (modelled after gmail_inbox_guardian):

  PRIMARY FLOW:   generic  (self-loop, user converses forever)
  ASYNC PIPELINE: intake -> fetch -> analyze -> dump -> (loop) -> report

Shared memory connects both flows:
  - generic writes triage_config -> intake reads it
  - report saves report.txt   -> generic reads it via load_data

The async pipeline is triggered on a scheduled timer.
The user can keep chatting with generic while triage runs in the background.
"""

from framework.graph import NodeSpec

# ---------------------------------------------------------------------------
# Node 0: Generic (PRIMARY -- client-facing, self-loop)
# ---------------------------------------------------------------------------
generic_node = NodeSpec(
    id="generic",
    name="Generic",
    description=(
        "Client-facing conversational hub. Sets triage config in shared memory, "
        "reads past triage results from files, answers user questions."
    ),
    node_type="event_loop",
    client_facing=True,
    max_node_visits=0,
    input_keys=[],
    output_keys=["triage_config"],
    system_prompt="""\
You are the Issue Triage Agent for the adenhq/hive repository.

You are the conversational hub. Users chat with you directly.
The triage pipeline (fetch, analyze, score, email) runs in the BACKGROUND
on a scheduled timer, separate from this conversation.

== WHAT YOU CAN DO ==

1. CHAT: Answer questions about the agent, triage process, GitHub issues, etc.

2. SET TRIAGE CONFIG: When the user wants to triage issues, parse their request
   and call set_output("triage_config", <JSON string>):
   {"mode": "triage", "lookback_hours": 24, "send_email": true}

   Parse timeframes: "24 hours"->24, "7 days"->168, "today"->24,
   "this week"->168, "2 weeks"->336. Default: 24 hours.
   mode: "triage" (default) or "stale" (if user mentions stale/inactive/zombie)
   send_email: true by default, false only if user says no.

   After saving config, tell the user:
   "Config saved! The background triage pipeline runs every 5 minutes
   and will pick this up on its next scheduled run."

3. READ PAST RESULTS: When the user asks about results ("how many issues?",
   "what did you find?", "show me the report"):
   - Call list_data_files() to see what files exist
   - Call load_data(filename="report.txt") to read the latest triage report
   - Answer the user's question based on the file contents
   - If no report.txt exists yet, tell the user:
     "No triage results available yet. The background pipeline runs every
     5 minutes. Check back shortly after configuring a triage run."

== WHEN THE USER FIRST ARRIVES ==

Greet them briefly. Mention capabilities:
- Set triage config (e.g. "triage last 24 hours")
- Ask about past triage results
- Chat about anything

== ROUTING KEYWORDS -- call set_output for these ==

When the user says anything involving:
- "triage", "check", "scan", "find", "get", "fetch", "list" + issues
- Time windows: "last 24 hours", "today", "this week", "7 days"
- "stale", "inactive", "zombie"
- "run", "start", "go"

Do: parse their intent, set_output("triage_config", {...}), and confirm.

If user asks about results AT THE SAME TIME (e.g. "how many issues in last 24h"):
  1. First try load_data("report.txt") to answer from past results
  2. Also set_output("triage_config", {...}) to schedule a fresh run

== RULES ==
- You have NO GitHub API tools. Cannot fetch issues directly.
- You have NO ChromaDB tools. Cannot search or upsert.
- You CAN read files saved by the background pipeline (load_data, list_data_files).
- NEVER say "I need data", "provide me with", "I require", "please provide".
- If user wants triage, set the config. Don't refuse or ask for data.
- Be conversational, helpful, and responsive.
""",
    tools=["load_data", "list_data_files", "get_current_time"],
)

# ---------------------------------------------------------------------------
# Node 1: Intake (ASYNC PIPELINE -- background, not client-facing)
# ---------------------------------------------------------------------------
intake_node = NodeSpec(
    id="intake",
    name="Intake",
    description=(
        "Background: read triage config from shared memory, dual-fetch ALL issues, "
        "filter, detect stale, output issue queue for per-issue processing."
    ),
    node_type="event_loop",
    max_node_visits=0,
    input_keys=["triage_config"],
    output_keys=["issue_queue", "triage_results"],
    nullable_output_keys=["issue_queue", "triage_results"],
    system_prompt="""\
You are the intake node for the Issue Triage Agent. You run in the BACKGROUND.

Your input message contains triage_config as a JSON object set by the user
via the generic node. Parse it to get: mode, lookback_hours, send_email.

If triage_config is missing, empty, null, or just "Begin.", use defaults:
  mode="triage", lookback_hours=24, send_email=true

STEP 1 -- Dual-fetch ALL issues:

Call get_current_time() first. Calculate: since = now - lookback_hours (ISO 8601).

FETCH A -- Updated issues:
  github_list_issues(owner="adenhq", repo="hive", state="open",
    sort="updated", direction="desc", limit=100, page=1, since=<since>)
  Response: {"success": true, "data": [...]}.
  Paginate (increment page) until data array has < 100 entries.

FETCH B -- Created issues:
  github_list_issues(owner="adenhq", repo="hive", state="open",
    sort="created", direction="desc", limit=100, page=1)
  Response: {"success": true, "data": [...]}.
  Keep only issues where created_at >= since. Stop when created_at < since.

Merge + deduplicate by issue number.
Track: total_fetched, created_count, updated_only_count.

FILTER: Remove entries where is_pull_request==true OR labels contain
"invalid"/"wontfix"/"question"/"spam" OR state=="closed".
Track skipped_count. Remaining = candidates.

STEP 2 -- Stale detection:
  github_list_issues(owner="adenhq", repo="hive", assignee="*",
    state="open", sort="updated", direction="asc", limit=100)
  Keep issues where is_pull_request==false AND updated_at older than 14 days ago.

STEP 3 -- Save summary to file for the user to read:
  save_data(filename="fetch_summary.txt", data=<formatted summary>):
  "Fetch Summary for last {lookback_hours} hours:
    Total found: {total_fetched}
    Created: {created_count} | Updated: {updated_only_count}
    Skipped: {skipped_count} | Candidates: {len(candidates)}
    Issues: #{n1}, #{n2}, #{n3}, ...
    Stale: {stale_count}"

STEP 4 -- Output:

IF candidates is empty:
  set_output("triage_results", <JSON string>):
  {"mode": "...", "all_issue_numbers": [], "fetch_summary": {...},
   "high_value_issues": [], "stale_issues": [...], "total_analyzed": 0,
   "total_skipped": N, "total_upserted": 0, "send_email": bool}

IF candidates is NOT empty:
  set_output("issue_queue", <JSON string>):
  {"config": {"mode": "triage", "lookback_hours": N, "send_email": bool},
   "fetch_summary": {"total_fetched": N, "created_count": N,
     "updated_only_count": N, "skipped_count": N},
   "stale_issues": [{number, title, url, assignee, updated_at}, ...],
   "candidates": [{number, title, url, labels, created_at, updated_at, state}, ...],
   "current_index": 0,
   "all_issue_numbers": [],
   "high_value_issues": [],
   "total_analyzed": 0,
   "total_upserted": 0}

For STALE mode only: skip dual-fetch, do stale detection, output triage_results.

RULES:
- You are a background node. Do NOT use ask_user(). Do NOT ask questions.
- ALWAYS do BOTH fetches (A + B) for triage mode.
- Paginate until done.
- Issue data is in the "data" array of the response.
- Just do the work and call set_output.
""",
    tools=["github_list_issues", "get_current_time", "save_data"],
)

# ---------------------------------------------------------------------------
# Node 2: Fetch -- ONE issue content enrichment (ASYNC PIPELINE loop member)
# ---------------------------------------------------------------------------
fetch_node = NodeSpec(
    id="fetch",
    name="Fetch",
    description="Fetch full content for ONE GitHub issue: body, comments, timeline, linked PRs.",
    node_type="event_loop",
    input_keys=["issue_queue"],
    output_keys=["enriched_issue"],
    nullable_output_keys=["enriched_issue"],
    max_node_visits=0,
    system_prompt="""\
You fetch detailed content for ONE GitHub issue.

Your input message contains issue_queue as a JSON object.
Parse it. Get the candidate at candidates[current_index].
That is the ONE issue you process. Use owner="adenhq", repo="hive" for all calls.

STEP 1: github_get_issue(owner="adenhq", repo="hive", issue_number=<number>)
  Response: {"success": true, "data": {...}}. Extract title, body, labels, state.

STEP 2: github_get_issue_comments(owner="adenhq", repo="hive", issue_number=<number>)
  Response: {"success": true, "data": [...]}. Extract comments (user, body, created_at).

STEP 3: github_get_issue_timeline(owner="adenhq", repo="hive", issue_number=<number>)
  Response: {"success": true, "data": [...]}. Extract timeline events.

STEP 4: From timeline, find cross-references where event=="cross-referenced" and
  source.is_pull_request==true. Get PR numbers from source.issue_number.
  For up to 3 PRs: github_get_pull_request(owner="adenhq", repo="hive", pull_number=<N>)

STEP 5: Build outcome_text:
  - Merged PR -> "SOLVED: Merged via PR #X"
  - Closed PR -> "FAILED_ATTEMPT: PR #X closed"
  - Open PR -> "IN_PROGRESS: PR #X open"
  - No PRs -> "No linked PRs."

STEP 6: Build full_text = title + "\\n\\n" + (body or "No description.")
  Append up to 10 comments: "\\n\\nComments:\\n" + comment bodies
  Append: "\\n\\nOUTCOME: " + outcome_text

STEP 7: set_output("enriched_issue", <JSON string>):
  {"number": N, "title": "...", "body": "...", "labels": "...",
   "created_at": "...", "state": "...", "url": "...",
   "full_text": "...", "outcome_text": "...",
   "has_merged_pr": true/false, "comments_count": N}

RULES:
- Process EXACTLY ONE issue. No more, no less.
- If a tool call fails, note the error and continue with available data.
- Do NOT touch ChromaDB. Do NOT score. Just fetch and set_output.
- Do NOT ask the user anything. You are an internal background node.
""",
    tools=[
        "github_get_issue",
        "github_get_issue_comments",
        "github_get_issue_timeline",
        "github_get_pull_request",
    ],
)

# ---------------------------------------------------------------------------
# Node 3: Analyze -- ONE issue scoring (ASYNC PIPELINE loop member)
# ---------------------------------------------------------------------------
analyze_node = NodeSpec(
    id="analyze",
    name="Analyze",
    description="Score ONE issue against ChromaDB: novelty, severity, impact.",
    node_type="event_loop",
    input_keys=["enriched_issue"],
    output_keys=["scored_issue"],
    nullable_output_keys=["scored_issue"],
    max_node_visits=0,
    system_prompt="""\
You score ONE issue against the ChromaDB knowledge base.

Your input message contains enriched_issue as a JSON object.
Parse it. It has: number, title, full_text, labels, body, outcome_text, etc.

STEP 1: Search knowledge base:
  vector_db_search(query_texts=[<full_text>], n_results=5,
    collection_name="issue_knowledge_base")
  Extract "summary" from each result's metadatas.
  If error or empty results -> treat as no prior matches (that is fine).

STEP 2: Score the issue:
  - is_semantic_duplicate: true ONLY if same root cause as a KB issue
  - novelty_score: 1-10  (1-3=duplicate, 4-6=similar, 7-8=mostly new, 9-10=unique)
    If KB is empty or no matches -> score 8+
  - severity: "Critical" | "High" | "Medium" | "Low"
    crash/data-loss/security -> Critical, broken feature -> High,
    cosmetic/docs -> Medium/Low
  - impact_score: novelty * 10, +20 if Critical, +10 if High. Cap at 100.
  - summary: one sentence summary
  - reasoning: 1-2 sentences explaining your assessment

STEP 3: Determine is_high_value:
  true if (novelty >= 8 OR impact >= 80) AND NOT is_semantic_duplicate

STEP 4: set_output("scored_issue", <JSON string>):
  Include ALL fields from enriched_issue PLUS:
  {"...all enriched_issue fields...",
   "novelty_score": N, "severity": "...", "impact_score": N,
   "summary": "...", "reasoning": "...",
   "is_duplicate": bool, "is_high_value": bool}

RULES:
- Process EXACTLY the one issue from enriched_issue.
- Do NOT upsert to ChromaDB. The dump node does that.
- Do NOT fabricate scores -- base them on search results.
- Do NOT ask the user anything. You are an internal background node.
""",
    tools=["vector_db_search"],
)

# ---------------------------------------------------------------------------
# Node 4: Dump -- ONE issue ChromaDB upsert + loop control (ASYNC PIPELINE)
# ---------------------------------------------------------------------------
dump_node = NodeSpec(
    id="dump",
    name="Dump",
    description=(
        "Upsert ONE scored issue to ChromaDB (maintainer_service format), "
        "update queue, route: loop back to fetch or forward to report."
    ),
    node_type="event_loop",
    input_keys=["scored_issue", "issue_queue"],
    output_keys=["issue_queue", "triage_results"],
    nullable_output_keys=["issue_queue", "triage_results"],
    max_node_visits=0,
    system_prompt="""\
You upsert ONE issue to ChromaDB and control the processing loop.

Your input message contains both scored_issue and issue_queue as JSON.
Parse both.

STEP 1 -- Upsert to ChromaDB:
  vector_db_upsert(
    ids=[str(scored_issue.number)],
    documents=[scored_issue.full_text],
    metadatas=[{"title": scored_issue.title, "state": scored_issue.state,
      "has_merged_pr": scored_issue.has_merged_pr, "labels": scored_issue.labels,
      "created_at": scored_issue.created_at, "summary": scored_issue.summary}],
    collection_name="issue_knowledge_base")

STEP 2 -- Write progress to file:
  append_data(filename="triage_progress.jsonl", data=<JSON line>):
  {"number": N, "title": "...", "severity": "...", "novelty_score": N,
   "impact_score": N, "is_high_value": bool, "summary": "..."}

STEP 3 -- Update queue state. Modify issue_queue:
  - Append scored_issue.number to all_issue_numbers
  - If scored_issue.is_high_value: append to high_value_issues (include number,
    title, url, novelty_score, impact_score, severity, summary, reasoning,
    labels, has_merged_pr)
  - Increment total_analyzed by 1
  - Increment total_upserted by 1
  - Set current_index = current_index + 1

STEP 4 -- Decide: loop or finish. Call set_output EXACTLY ONCE:

  IF current_index < len(candidates):
    set_output("issue_queue", <updated issue_queue JSON>)
    (This loops back to fetch for the next issue.)

  IF current_index >= len(candidates):
    set_output("triage_results", <JSON string>):
    {"mode": "triage", "all_issue_numbers": [...], "fetch_summary": {...},
     "high_value_issues": [...], "stale_issues": [...],
     "total_analyzed": N, "total_skipped": fetch_summary.skipped_count,
     "total_upserted": N, "send_email": config.send_email}
    (This forwards to the report node.)

RULES:
- ALWAYS upsert. Every issue goes into ChromaDB.
- ALWAYS write progress to triage_progress.jsonl.
- Call set_output EXACTLY ONCE: either "issue_queue" (loop) or "triage_results" (done).
- Do NOT ask the user anything. You are an internal background node.
""",
    tools=["vector_db_upsert", "append_data"],
)

# ---------------------------------------------------------------------------
# Node 5: Report (ASYNC PIPELINE -- background, not client-facing)
# ---------------------------------------------------------------------------
report_node = NodeSpec(
    id="report",
    name="Report",
    description=(
        "Background: generate triage report, save to file for generic node to read, "
        "send HTML email digest. Does NOT block for user input."
    ),
    node_type="event_loop",
    max_node_visits=0,
    input_keys=["triage_results"],
    output_keys=["last_triage_report"],
    system_prompt="""\
You are the report node for the Issue Triage Agent. You run in the BACKGROUND.

Your input message contains triage_results as a JSON object.
Parse it. It has: mode, all_issue_numbers, fetch_summary, high_value_issues,
stale_issues, total_analyzed, total_upserted, send_email.

STEP 1 -- Build the text report:

For TRIAGE mode build this text:

  === Issue Triage Report ===
  Generated: {current timestamp}

  Triage Summary:
  - Issues analyzed: {total_analyzed}
  - Issues upserted to knowledge base: {total_upserted}
  - High-value issues found: {len(high_value_issues)}
  - Stale issues found: {len(stale_issues)}

  Fetch Breakdown:
  - Total issues found: {fetch_summary.total_fetched}
  - Newly created in window: {fetch_summary.created_count}
  - Updated (existing with new activity): {fetch_summary.updated_only_count}
  - Skipped (PRs/spam/closed): {fetch_summary.skipped_count}

  All issues found: #{n1}, #{n2}, #{n3}, ...

  High-Value Issues (sorted by impact_score descending):
  For each:
    [{severity}] #{number}: {title}
      Impact: {impact_score}/100 | Novelty: {novelty_score}/10
      Summary: {summary}
      Analysis: {reasoning}

  Stale Issues (assigned but inactive 14+ days):
  For each: #{number}: {title} -- assigned to @{assignee}, last updated {updated_at}

  If no high-value issues: "No high-value issues found."
  If no stale issues: "No stale issues found."

For STALE mode: list stale issues with assignees and last update dates.

STEP 2 -- Save the report:
  save_data(filename="report.txt", data=<the full text report>)

STEP 3 -- Send email if send_email is true AND there are high_value or stale issues.

Build an HTML email. Group high-value issues by category based on labels:
- Bugs: labels containing "bug" or "critical"
- Enhancements: labels containing "enhancement" or "feature"
- Integrations: labels containing "integration" or "tools"
- Security: labels containing "security"
- Documentation: labels containing "documentation"
- Other: everything else

Sort within each category by impact_score descending.

Use this HTML template:

<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
<div style="background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">

  <h1 style="color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 15px; margin-bottom: 25px;">
    Issue Triage Digest
  </h1>

  <div style="background: #f0f4ff; border-radius: 8px; padding: 15px; margin-bottom: 25px;">
    <strong>Summary</strong><br>
    Issues analyzed: {total_analyzed} | Upserted: {total_upserted}<br>
    Fetched: {total_fetched} (Created: {created_count} | Updated: {updated_only_count})<br>
    Skipped: {skipped_count} | High-value: {hv_count} | Stale: {stale_count}
  </div>

  <!-- For EACH category with issues add a section header -->
  <h2 style="color: #16213e; margin-top: 30px;">Bugs</h2>

  <!-- For EACH issue in the category: -->
  <div style="border-left: 4px solid {border_color}; background: {bg_color}; padding: 15px; margin: 10px 0; border-radius: 0 8px 8px 0;">
    <span style="background: {severity_bg}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">
      {SEVERITY}
    </span>
    <a href="{url}" style="color: #1a1a2e; text-decoration: none; font-weight: 600; font-size: 16px; margin-left: 8px;">
      #{number}: {title}
    </a>
    <div style="margin-top: 8px; color: #555; font-size: 14px;">
      Impact: {impact}/100 | Novelty: {novelty}/10 | Severity: {severity}
    </div>
    <div style="margin-top: 5px; color: #333; font-size: 14px;">
      {summary}
    </div>
    <div style="margin-top: 5px; color: #666; font-size: 13px; font-style: italic;">
      {reasoning}
    </div>
  </div>

  <!-- Severity badge colors:
       Critical: badge bg #dc3545, border #dc3545, card bg #fff5f5
       High: badge bg #fd7e14, border #fd7e14, card bg #fff8f0
       Medium: badge bg #ffc107 text #333, border #ffc107, card bg #fffdf0
       Low: badge bg #28a745, border #28a745, card bg #f0fff4 -->

  <!-- Stale section (if stale_issues exist): -->
  <div style="background: #fff3cd; border: 2px solid #daa520; border-radius: 8px; padding: 20px; margin-top: 30px;">
    <h2 style="color: #856404; margin-top: 0;">STALLED: Inactive Assignees ({stale_count})</h2>
    <p style="color: #856404;">These issues are assigned but inactive for 14+ days.</p>
    <div style="background: white; padding: 12px; margin: 8px 0; border-radius: 6px; border-left: 3px solid #daa520;">
      <a href="{url}" style="color: #1a1a2e; text-decoration: none; font-weight: 600;">#{number}: {title}</a>
      <div style="color: #666; font-size: 13px; margin-top: 4px;">
        Assigned to @{assignee} -- Last updated: {updated_at}
      </div>
    </div>
  </div>

  <div style="margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; color: #999; font-size: 12px;">
    Generated by Issue Triage Agent -- adenhq/hive
  </div>

</div>
</body>
</html>

Send the email:
  send_email(
    to=NOTIFICATION_EMAIL,
    subject="Issue Triage Digest: {count} Items Requiring Attention",
    html=<the fully built HTML string>,
    from_email=SMTP_USERNAME,
    provider="smtp")

STEP 4 -- Finalize:
  set_output("last_triage_report", "report.txt")

RULES:
- You are a background node. Do NOT use ask_user(). Do NOT block for input.
- ALWAYS save report.txt via save_data BEFORE sending email.
- Generate report, save, email, set_output. Then you are done.
""",
    tools=["send_email", "save_data", "load_data", "get_current_time"],
)

__all__ = [
    "generic_node",
    "intake_node",
    "fetch_node",
    "analyze_node",
    "dump_node",
    "report_node",
]
