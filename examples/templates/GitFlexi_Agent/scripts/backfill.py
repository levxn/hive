"""
Backfill Script for GitFlexi Agent.
Backfills historical GitHub issues into ChromaDB to build the knowledge base.
Usage: python -m examples.templates.GitFlexi_Agent.scripts.backfill --days 30
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from litellm import completion

# Adjust path to import from agent package and root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
sys.path.insert(0, project_root)

from examples.templates.GitFlexi_Agent.config import settings, default_config
from tools.src.aden_tools.tools.vector_db_tool.stores.chromadb import ChromaDBStore
from tools.src.aden_tools.tools.github_tool.github_tool import _GitHubClient

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Backfiller:
    def __init__(self):
        # 1. Initialize GitHub Client
        if not settings.github_token:
            raise ValueError("GITHUB_TOKEN not found in settings or environment.")
        self.gh = _GitHubClient(settings.github_token)

        # 2. Initialize Vector Store
        db_path = os.path.expanduser(settings.chroma_persist_directory)
        self.vector_store = ChromaDBStore(
            collection_name=settings.chroma_collection_name,
            persist_directory=db_path
        )
        logger.info(f"Initialized ChromaDB at {db_path}")

    def get_issues(self, owner, repo, since):
        """Fetch all issues since timestamp."""
        all_issues = []
        page = 1
        while True:
            logger.info(f"Fetching page {page}...")
            res = self.gh.list_issues(
                owner=owner, repo=repo, state="all", 
                since=since, page=page, limit=100
            )
            
            if "error" in res:
                logger.error(f"Error fetching issues: {res['error']}")
                break
                
            batch = res.get("data", [])
            if not batch:
                break
                
            all_issues.extend(batch)
            logger.info(f"Fetched {len(batch)} issues (Total: {len(all_issues)})")
            
            if len(batch) < 100:
                break
            page += 1
            
        return all_issues

    def get_timeline_summary(self, owner, repo, issue_number):
        """Fetch timeline and extract PR status."""
        res = self.gh.get_issue_timeline(owner, repo, issue_number)
        if "error" in res:
            return [], False
            
        events = res.get("data", [])
        pr_statuses = []
        has_merged = False
        
        # Simple extraction of referenced PRs (cross-referenced events)
        seen_prs = set()
        for event in events:
            if event["event"] in ["cross-referenced", "connected"]:
                source = event.get("source", {}).get("issue", {})
                if source.get("pull_request") and source["number"] not in seen_prs:
                    pr_num = source["number"]
                    seen_prs.add(pr_num)
                    
                    # Fetch PR details
                    pr_res = self.gh.get_pull_request(owner, repo, pr_num)
                    if "data" in pr_res:
                        pr = pr_res["data"]
                        merged = pr.get("merged", False)
                        if merged: has_merged = True
                        pr_statuses.append(f"PR #{pr_num}: {pr.get('state')} (Merged: {merged})")
        
        return pr_statuses, has_merged

    def generate_summary(self, text):
        """Generate short summary using LiteLLM."""
        try:
            response = completion(
                model=default_config.model,
                messages=[{
                    "role": "user", 
                    "content": f"Summarize this GitHub issue and its outcome in 1 sentence:\n\n{text[:4000]}"
                }]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM summary failed: {e}")
            return "No summary generated."

    def run(self, days):
        owner = settings.github_repo_owner
        repo = settings.github_repo_name
        
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        since_str = since_dt.isoformat()
        
        logger.info(f"Backfilling {owner}/{repo} since {since_str}")
        
        issues = self.get_issues(owner, repo, since_str)
        logger.info(f"Found {len(issues)} issues to process.")
        
        success_count = 0
        for i, issue in enumerate(issues, 1):
            try:
                num = issue["number"]
                title = issue["title"]
                body = issue["body"] or ""
                
                logger.info(f"[{i}/{len(issues)}] Processing #{num}: {title[:30]}...")
                
                # Fetch Timeline/PRs
                pr_status_list, has_merged_pr = self.get_timeline_summary(owner, repo, num)
                
                full_text = f"Title: {title}\nBody: {body}\nPRs: {'; '.join(pr_status_list)}"
                
                # Generate Summary
                summary = self.generate_summary(full_text)
                
                # Construct Metadata
                labels = [l["name"] for l in issue.get("labels", [])]
                metadata = {
                    "title": title,
                    "state": issue["state"],
                    "has_merged_pr": has_merged_pr,
                    "labels": ", ".join(labels),
                    "created_at": issue["created_at"],
                    "summary": summary,
                    "novelty_score": 0, # Historical, assume low novelty or skip
                    "impact_score": 0   # Historical
                }
                
                # Upsert
                self.vector_store.upsert(
                    ids=[str(num)],
                    documents=[full_text],
                    metadatas=[metadata]
                )
                success_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process #{num}: {e}")
                
        logger.info(f"✅ Backfill complete. Success: {success_count}/{len(issues)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill GitFlexi Agent Knowledge Base")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backfill")
    args = parser.parse_args()
    
    backfiller = Backfiller()
    backfiller.run(args.days)
