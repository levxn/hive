"""Triage Node: Analyze issues using VectorDB and LLM."""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any

from framework.graph import NodeSpec, NodeContext, NodeResult, NodeProtocol
from aden_tools.tools.github_tool.github_tool import _GitHubClient
from aden_tools.tools.vector_db_tool.stores.chromadb import ChromaDBStore

# Try to import litellm, handle if not available (though it should be)
try:
    import litellm
except ImportError:
    litellm = None

logger = logging.getLogger(__name__)
UTC = timezone.utc

# --- Helper Functions (Ported from maintainer_service) ---

def extract_pr_info_from_timeline(timeline: list[dict]) -> list[dict]:
    """Extract linked PR information from timeline events."""
    pr_references = []
    for event in timeline:
        if event.get("event") == "cross-referenced":
            source = event.get("source", {})
            if source.get("type") == "issue" and "pull_request" in source.get("issue", {}):
                pr_number = source["issue"]["number"]
                pr_references.append({
                    "pr_number": pr_number,
                    "event_created_at": event.get("created_at")
                })
    return pr_references

def build_outcome_text(pr_statuses: list[dict]) -> str:
    """Build outcome text describing PR resolution status."""
    if not pr_statuses:
        return "No linked PRs found."
    
    merged_prs = [pr for pr in pr_statuses if pr.get("is_merged")]
    closed_prs = [pr for pr in pr_statuses if not pr.get("is_merged") and pr.get("state") == "closed"]
    open_prs = [pr for pr in pr_statuses if pr.get("state") == "open"]
    
    parts = []
    if merged_prs:
        pr_nums = ", ".join([f"#{pr['pr_number']}" for pr in merged_prs])
        parts.append(f"SOLVED: Merged via PR(s) {pr_nums}.")
    if closed_prs:
        pr_nums = ", ".join([f"#{pr['pr_number']}" for pr in closed_prs])
        parts.append(f"FAILED_ATTEMPT: PR(s) {pr_nums} closed without merge.")
    if open_prs:
        pr_nums = ", ".join([f"#{pr['pr_number']}" for pr in open_prs])
        parts.append(f"IN_PROGRESS: PR(s) {pr_nums} still open.")
    
    return " ".join(parts)

# --- Main Logic ---

class TriageNode(NodeProtocol):
    """
    Triage Node implementation.
    Analyzes issues using VectorDB and LLM.
    """
    async def execute(self, ctx: NodeContext) -> NodeResult:
        logger.info("Starting TriageNode execution")
        
        # 1. Inputs - Read from shared memory
        raw_issues = ctx.memory.read("raw_issues") or []
        stale_issues = ctx.memory.read("stale_issues") or []
        notification_email = ctx.memory.read("notification_email")
        owner = ctx.memory.read("owner")
        repo = ctx.memory.read("repo")
        
        if not owner or not repo:
            return NodeResult(success=False, error="Missing owner or repo in inputs")
            
        if not raw_issues and not stale_issues:
            logger.info("No issues to analyze.")
            return NodeResult(success=True, output={
                "analyzed_issues": [], 
                "stale_issues": stale_issues, 
                "notification_email": notification_email
            })

        # 2. Setup Clients
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            # Fallback
            token = ctx.memory.read("GITHUB_TOKEN")
            if not token:
                 return NodeResult(success=False, error="GITHUB_TOKEN not found")
        
        gh_client = _GitHubClient(token)
        
        # Initialize VectorDB
        try:
            from ..config import settings
            persist_dir = os.path.expanduser(settings.chroma_persist_directory)
            collection_name = settings.chroma_collection_name
            vector_store = ChromaDBStore(persist_directory=persist_dir, collection_name=collection_name)
        except Exception as e:
            return NodeResult(success=False, error=f"Failed to init ChromaDB: {e}")

        analyzed_issues = []
        
        # 3. Process Each Issue
        total = len(raw_issues)
        for i, issue_summary in enumerate(raw_issues):
            try:
                issue_number = issue_summary.get("number")
                logger.info(f"Analyzing issue #{issue_number} ({i+1}/{total})")
                
                if not issue_number:
                    continue

                # A. Fetch Full Details
                # Body
                issue_response = gh_client.get_issue(owner, repo, issue_number)
                if "error" in issue_response:
                    logger.error(f"Failed to get issue {issue_number}: {issue_response['error']}")
                    continue
                issue = issue_response["data"]
                
                # Helper to check if closed/spam (Filter logic from maintainer_service)
                if issue["state"] == "closed":
                    continue # Skip closed
                
                # Comments
                comments_resp = gh_client.get_issue_comments(owner, repo, issue_number)
                comments = comments_resp.get("data", []) if "data" in comments_resp else []
                
                # Timeline & PRs
                timeline_resp = gh_client.get_issue_timeline(owner, repo, issue_number)
                timeline = timeline_resp["data"] if "data" in timeline_resp else []
                
                pr_refs = extract_pr_info_from_timeline(timeline)
                pr_statuses = []
                for pr_ref in pr_refs[:5]: # Limit to 5 PRs
                    pr_resp = gh_client.get_pull_request(owner, repo, pr_ref["pr_number"])
                    if "data" in pr_resp:
                        pr_data = pr_resp["data"]
                        pr_statuses.append({
                            "pr_number": pr_ref["pr_number"],
                            "is_merged": pr_data.get("merged", False),
                            "merged_at": pr_data.get("merged_at"),
                            "state": pr_data.get("state")
                        })

                # B. Construct Full Text
                full_text = f"{issue['title']}\n\n{issue['body'] or ''}"
                if comments:
                    comment_text = "\\n\\n".join([c["body"] for c in comments[:10]])
                    full_text += f"\\n\\nComments:\\n{comment_text}"
                
                outcome_text = build_outcome_text(pr_statuses)
                full_text += f"\\n\\nOUTCOME: {outcome_text}"
                
                # C. Vector Search (Check for semantic duplicates)
                similar_summaries = []
                issue_id = str(issue_number)
                
                try:
                    # search() returns dict with 'data' key or 'error'
                    search_res = vector_store.search([full_text], n_results=5)
                    if search_res.get("success"):
                        # Extract summaries from metadata
                        # results structure: {'ids': [['id1', ...]], 'metadatas': [[{'summary':...}, ...]]}
                        data = search_res["data"]
                        metadatas = data["metadatas"][0] if data.get("metadatas") else []
                        ids = data["ids"][0] if data.get("ids") else []
                        
                        for idx, meta in enumerate(metadatas):
                            if ids[idx] != issue_id: # Exclude self
                                if meta and meta.get("summary"):
                                    similar_summaries.append(meta.get("summary"))
                except Exception as e:
                    logger.warning(f"Vector search failed: {e}")

                # D. LLM Analysis
                summaries_text = "\\n".join([f"{j+1}. {s}" for j, s in enumerate(similar_summaries)])
                
                prompt = f"""
Candidate Issue:
{full_text[:300]}

Similar Past Issues:
{summaries_text}

Analyze:
"""
                system_prompt = """Analyze if this GitHub issue is novel compared to existing issues and assess its IMPACT.

Output JSON with:
- is_semantic_duplicate: boolean
- novelty_score: 1-10 (8+ only for NEW scope or critical UNKNOWN bugs)
- severity: "Current Critical", "High", "Medium", "Low"
- reasoning: brief explanation
- one_sentence_summary: concise summary"""

                # Call LLM
                analysis = {}
                if litellm:
                    try:
                        # Use configured model or fallback
                        model = ctx.llm.model if ctx.llm and ctx.llm.model else "gpt-3.5-turbo"
                        
                        response = litellm.completion(
                            model=model, 
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            response_format={"type": "json_object"},
                            temperature=0.2
                        )
                        content = response.choices[0].message.content
                        analysis = json.loads(content)
                    except Exception as e:
                        logger.error(f"LLM call failed: {e}")
                        analysis = {"novelty_score": 0, "summary": f"Analysis failed: {e}", "is_semantic_duplicate": False}
                else:
                    # Fallback if litellm missing (should not happen in this env)
                    analysis = {"novelty_score": 0, "summary": "Analysis failed (no litellm)", "is_semantic_duplicate": False}

                # E. Upsert
                summary = analysis.get("one_sentence_summary", "")
                has_merged_pr = any(pr.get("is_merged") for pr in pr_statuses)
                labels_str = ", ".join([l["name"] for l in issue.get("labels", [])])
                
                # F. High Value Filter
                novelty = analysis.get("novelty_score", 0)
                severity = analysis.get("severity", "Low")
                impact_score = novelty * 10
                if severity == "Current Critical": impact_score += 20
                elif severity == "High": impact_score += 10
                impact_score = min(impact_score, 100)
                
                logger.info(f"Analyzed #{issue_number}: Novelty={novelty}, Severity={severity}, Impact={impact_score}")

                try:
                    logger.info(f"Upserting issue {issue_id} to ChromaDB at {persist_dir}...")
                    upsert_res = vector_store.upsert(
                        ids=[issue_id],
                        documents=[full_text],
                        metadatas=[{
                            "title": issue["title"],
                            "state": issue["state"],
                            "has_merged_pr": has_merged_pr,
                            "labels": labels_str,
                            "created_at": issue["created_at"],
                            "summary": summary,
                            "novelty_score": novelty,
                            "impact_score": impact_score
                        }]
                    )
                    logger.info(f"Upsert result: {upsert_res}")
                except Exception as e:
                    logger.error(f"Upsert failed: {e}")
                
                # Threshold from maintainer_service
                if (novelty >= 8 or impact_score >= 70) and not analysis.get("is_semantic_duplicate"):
                    logger.info(f"Issue #{issue_number} IS High Value! Adding to report.")
                    analyzed_issues.append({
                        "issue_id": issue_id,
                        "number": issue_number,
                        "title": issue["title"],
                        "url": issue["html_url"],
                        "novelty_score": novelty,
                        "impact_score": impact_score,
                        "severity": severity,
                        "summary": summary,
                        "reasoning": analysis.get("reasoning", ""),
                        "labels": issue.get("labels", [])
                    })
                    
            except Exception as e:
                logger.error(f"Error processing issue {issue_summary.get('number')}: {e}")
                continue

        logger.info(f"Analysis complete. Found {len(analyzed_issues)} high-value issues.")
        
        return NodeResult(success=True, output={
            "analyzed_issues": analyzed_issues,
            "stale_issues": stale_issues, 
            "notification_email": notification_email
        })


triage_node = NodeSpec(
    id="triage",
    name="Triage Issues",
    description="Analyze issues for novelty and severity using full context (comments, timeline, PR details).",
    node_type="function",
    function="examples.templates.GitFlexi_Agent.nodes.triage.TriageNode",
    input_keys=["raw_issues", "stale_issues", "notification_email", "owner", "repo"],
    output_keys=["analyzed_issues", "stale_issues", "notification_email"],
    client_facing=False
)

