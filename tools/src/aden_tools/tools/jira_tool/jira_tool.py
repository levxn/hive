"""
Jira Tool - Manage issues, attachments, users, and worklogs via Jira REST API.

Supports:
- Jira Cloud with API token (JIRA_EMAIL + JIRA_API_TOKEN)
- Jira Server/Data Center with PAT (JIRA_PAT)

Requires JIRA_BASE_URL environment variable.
API Reference: https://developer.atlassian.com/cloud/jira/platform/rest/v3/
"""

from __future__ import annotations

import base64
import os
from typing import TYPE_CHECKING, Any

import httpx
from fastmcp import FastMCP

if TYPE_CHECKING:
    from aden_tools.credentials import CredentialStoreAdapter


class _JiraClient:
    """Internal client wrapping Jira REST API v3 calls."""

    def __init__(self, base_url: str, email: str | None, api_token: str):
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._api_token = api_token

    @property
    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # Cloud: Basic Auth with email:token
        if self._email:
            auth_str = f"{self._email}:{self._api_token}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            headers["Authorization"] = f"Basic {auth_b64}"
        else:
            # Server/DC: Bearer token (PAT)
            headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    def _multipart_headers(self) -> dict[str, str]:
        """Headers for multipart/form-data requests (attachments)."""
        headers = {"Accept": "application/json", "X-Atlassian-Token": "no-check"}
        if self._email:
            auth_str = f"{self._email}:{self._api_token}"
            auth_b64 = base64.b64encode(auth_str.encode()).decode()
            headers["Authorization"] = f"Basic {auth_b64}"
        else:
            headers["Authorization"] = f"Bearer {self._api_token}"
        return headers

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle Jira API response format."""
        if response.status_code == 401:
            return {"error": "Invalid Jira credentials. Check JIRA_EMAIL and JIRA_API_TOKEN."}
        if response.status_code == 403:
            return {"error": "Forbidden - check permissions or API token scopes."}
        if response.status_code == 404:
            return {"error": "Resource not found. Check issue key or project key."}
        if response.status_code == 429:
            return {"error": "Rate limit exceeded. Try again later."}
        if response.status_code >= 400:
            try:
                errors = response.json().get("errorMessages", [])
                detail = "; ".join(errors) if errors else response.text
            except Exception:
                detail = response.text
            return {"error": f"Jira API error (HTTP {response.status_code}) at {response.url}: {detail}"}

        try:
            data = response.json()
            return {"success": True, "data": data}
        except Exception:
            return {"success": True, "data": {}}

    # ===== Issues =====

    def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str | None = None,
        assignee_account_id: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Jira issue."""
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }
        if description:
            # Jira Cloud uses Atlassian Document Format (ADF) for description
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}
        if priority:
            fields["priority"] = {"name": priority}
        if labels:
            fields["labels"] = labels

        response = httpx.post(
            f"{self._base_url}/rest/api/3/issue",
            headers=self._headers,
            json={"fields": fields},
            timeout=30.0,
        )
        return self._handle_response(response)

    def get_issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get issue by key (e.g., PROJ-123)."""
        params = {}
        if fields:
            params["fields"] = ",".join(fields)

        response = httpx.get(
            f"{self._base_url}/rest/api/3/issue/{issue_key}",
            headers=self._headers,
            params=params,
            timeout=30.0,
        )
        return self._handle_response(response)

    def update_issue(
        self,
        issue_key: str,
        summary: str | None = None,
        description: str | None = None,
        assignee_account_id: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        fields: dict[str, Any] = {}
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}
        if priority:
            fields["priority"] = {"name": priority}
        if labels is not None:
            fields["labels"] = labels

        if not fields:
            return {"error": "No fields to update"}

        response = httpx.put(
            f"{self._base_url}/rest/api/3/issue/{issue_key}",
            headers=self._headers,
            json={"fields": fields},
            timeout=30.0,
        )

        # Jira returns 204 No Content on success
        if response.status_code == 204:
            return {"success": True, "issue_key": issue_key}
        return self._handle_response(response)

    def search_issues(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Search issues using JQL."""
        if fields is None:
             # Default fields if none provided (key, summary, status are critical)
             fields = ["key", "summary", "status", "assignee"]
             
        body: dict[str, Any] = {
            "jql": jql,
            "maxResults": min(max_results, 100),
        }
        if fields:
            body["fields"] = fields

        # NOTE: Updated to new JQL search endpoint
        response = httpx.post(
            f"{self._base_url}/rest/api/3/search/jql",
            headers=self._headers,
            json=body,
            timeout=30.0,
        )
        
        result = self._handle_response(response)
        if "error" in result:
             return result
             
        # Enhance response for Agent consumption
        # The new JQL API returns { "issues": [ { "id": "...", "key": "...", "fields": {...} } ] }
        data = result.get("data", {})
        issues = data.get("issues", [])
        
        simplified_issues = []
        for issue in issues:
             # Extract critical identifier
             key = issue.get("key") # New API usually returns key at top level too? verifying..
             # If key is missing at top level, check where it is.
             # Actually, if we look at standard v3 search, key is top level.
             # However, the user log showed only 'id'.
             # This suggests we need to ASK for 'key' in fields explicitly?
             # Or the response format is different.
             # The new API `search/jql` documentation says it returns "Issue Bean".
             # Issue Bean has ID, Key, Self, Fields.
             # Why did we only get IDs? Because the fields param was default (id only).
             # By asking for fields=["key", "summary"], we should get them.
             
             fields_data = issue.get("fields", {})
             simplified = {
                 "key": issue.get("key") or issue.get("id"), # Fallback to ID if key missing (unlikely if requested)
                 "id": issue.get("id"),
                 "summary": fields_data.get("summary", "No Summary"),
                 "status": fields_data.get("status", {}).get("name", "Unknown"),
                 "assignee": fields_data.get("assignee", {}).get("displayName", "Unassigned")
             }
             simplified_issues.append(simplified)
             
        return {
            "success": True,
            "count": len(simplified_issues),
            "issues": simplified_issues,
            "original_data": data # Keep full data just in case
        }

    def get_transitions(self, issue_key: str) -> dict[str, Any]:
        """Get available transitions for an issue."""
        response = httpx.get(
            f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self._headers,
            timeout=30.0,
        )
        return self._handle_response(response)

    def transition_issue(self, issue_key: str, transition_id: str) -> dict[str, Any]:
        """Transition an issue to a new status."""
        response = httpx.post(
            f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions",
            headers=self._headers,
            json={"transition": {"id": transition_id}},
            timeout=30.0,
        )
        if response.status_code == 204:
            return {"success": True, "issue_key": issue_key}
        return self._handle_response(response)

    # ===== Attachments =====

    def add_attachment(
        self,
        issue_key: str,
        filename: str,
        content_base64: str,
    ) -> dict[str, Any]:
        """Add attachment to an issue."""
        try:
            file_bytes = base64.b64decode(content_base64)
        except Exception as e:
            return {"error": f"Invalid base64 content: {e}"}

        files = {"file": (filename, file_bytes)}
        response = httpx.post(
            f"{self._base_url}/rest/api/3/issue/{issue_key}/attachments",
            headers=self._multipart_headers(),
            files=files,
            timeout=60.0,
        )
        return self._handle_response(response)

    def list_attachments(self, issue_key: str) -> dict[str, Any]:
        """List attachments on an issue."""
        result = self.get_issue(issue_key, fields=["attachment"])
        if "error" in result:
            return result

        attachments = result.get("data", {}).get("fields", {}).get("attachment", [])
        return {
            "success": True,
            "issue_key": issue_key,
            "attachments": [
                {
                    "id": att.get("id"),
                    "filename": att.get("filename"),
                    "size": att.get("size"),
                    "mimeType": att.get("mimeType"),
                    "created": att.get("created"),
                    "author": att.get("author", {}).get("displayName"),
                }
                for att in attachments
            ],
        }

    # ===== Users =====

    def find_user(self, query: str, max_results: int = 10) -> dict[str, Any]:
        """Find users by email or display name."""
        response = httpx.get(
            f"{self._base_url}/rest/api/3/user/search",
            headers=self._headers,
            params={"query": query, "maxResults": min(max_results, 50)},
            timeout=30.0,
        )
        return self._handle_response(response)

    def get_myself(self) -> dict[str, Any]:
        """Get currently authenticated user."""
        response = httpx.get(
            f"{self._base_url}/rest/api/3/myself",
            headers=self._headers,
            timeout=30.0,
        )
        return self._handle_response(response)

    # ===== Worklogs =====

    def add_worklog(
        self,
        issue_key: str,
        time_spent: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Add worklog entry to an issue.
        
        Args:
            issue_key: Issue key (e.g., PROJ-123)
            time_spent: Jira duration format (e.g., "1h 30m", "2d", "45m")
            comment: Optional worklog comment
        """
        body: dict[str, Any] = {"timeSpent": time_spent}
        if comment:
            body["comment"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment}],
                    }
                ],
            }

        response = httpx.post(
            f"{self._base_url}/rest/api/3/issue/{issue_key}/worklog",
            headers=self._headers,
            json=body,
            timeout=30.0,
        )
        return self._handle_response(response)

    def list_worklogs(self, issue_key: str) -> dict[str, Any]:
        """List worklogs for an issue."""
        response = httpx.get(
            f"{self._base_url}/rest/api/3/issue/{issue_key}/worklog",
            headers=self._headers,
            timeout=30.0,
        )
        return self._handle_response(response)

    # ===== Projects =====

    def list_projects(self, max_results: int = 50) -> dict[str, Any]:
        """List accessible projects."""
        response = httpx.get(
            f"{self._base_url}/rest/api/3/project/search",
            headers=self._headers,
            params={"maxResults": min(max_results, 100)},
            timeout=30.0,
        )
        return self._handle_response(response)


def register_tools(
    mcp: FastMCP,
    credentials: CredentialStoreAdapter | None = None,
) -> None:
    """Register Jira tools with the MCP server."""

    def _get_config() -> tuple[str | None, str | None, str | None]:
        """Get Jira configuration from credentials or environment."""
        if credentials is not None:
            base_url = credentials.get("jira_base_url")
            email = credentials.get("jira_email")
            token = credentials.get("jira_api_token") or credentials.get("jira_pat")
            return base_url, email, token
        return (
            os.getenv("JIRA_BASE_URL"),
            os.getenv("JIRA_EMAIL"),
            os.getenv("JIRA_API_TOKEN") or os.getenv("JIRA_PAT"),
        )

    def _get_client() -> _JiraClient | dict[str, str]:
        """Get a Jira client, or return an error dict if not configured."""
        base_url, email, token = _get_config()
        if not base_url:
            return {
                "error": "Jira not configured",
                "help": "Set JIRA_BASE_URL (e.g., https://yourcompany.atlassian.net)",
            }
        if not token:
            return {
                "error": "Jira credentials not configured",
                "help": "Set JIRA_EMAIL + JIRA_API_TOKEN (Cloud) or JIRA_PAT (Server)",
            }
        return _JiraClient(base_url, email, token)

    # ===== Issues =====

    @mcp.tool()
    def jira_create_issue(
        project_key: str,
        issue_type: str,
        summary: str,
        description: str | None = None,
        assignee_account_id: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """
        Create a new Jira issue.

        Args:
            project_key: Project key (e.g., "PROJ", "ENG")
            issue_type: Issue type name (e.g., "Task", "Bug", "Story")
            summary: Issue title/summary
            description: Issue description (plain text)
            assignee_account_id: Jira account ID of assignee (use jira_find_user to get ID)
            priority: Priority name (e.g., "High", "Medium", "Low")
            labels: List of label names

        Returns:
            Dict with created issue key and ID, or error
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.create_issue(
                project_key, issue_type, summary, description,
                assignee_account_id, priority, labels
            )
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_get_issue(
        issue_key: str,
        fields: list[str] | None = None,
    ) -> dict:
        """
        Get a Jira issue by key.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            fields: Specific fields to return (e.g., ["summary", "status", "assignee"])

        Returns:
            Dict with issue data or error
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.get_issue(issue_key, fields)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_update_issue(
        issue_key: str,
        summary: str | None = None,
        description: str | None = None,
        assignee_account_id: str | None = None,
        priority: str | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """
        Update an existing Jira issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            summary: New summary/title
            description: New description
            assignee_account_id: New assignee's account ID
            priority: New priority name
            labels: New list of labels (replaces existing)

        Returns:
            Dict with success status or error
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.update_issue(
                issue_key, summary, description,
                assignee_account_id, priority, labels
            )
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_search_issues(
        jql: str,
        fields: list[str] | None = None,
        max_results: int = 50,
    ) -> dict:
        """
        Search Jira issues using JQL.

        Args:
            jql: JQL query string
                Examples:
                - "project = PROJ AND status = Open"
                - "assignee = currentUser() AND resolution = Unresolved"
                - "labels = urgent AND created >= -7d"
            fields: Fields to return (default: key, summary, status, assignee)
            max_results: Maximum results (1-100, default 50)

        Returns:
            Dict with search results or error
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.search_issues(jql, fields, max_results)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_transition_issue(
        issue_key: str,
        transition_name: str | None = None,
        transition_id: str | None = None,
    ) -> dict:
        """
        Transition a Jira issue to a new status.

        Provide either transition_name OR transition_id. If transition_name
        is provided, the tool will look up the matching transition ID.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            transition_name: Target status name (e.g., "In Progress", "Done")
            transition_id: Transition ID (if known)

        Returns:
            Dict with success status or error
        """
        client = _get_client()
        if isinstance(client, dict):
            return client

        if not transition_name and not transition_id:
            return {"error": "Provide transition_name or transition_id"}

        try:
            if transition_name and not transition_id:
                # Look up transition ID by name
                transitions_result = client.get_transitions(issue_key)
                if "error" in transitions_result:
                    return transitions_result

                transitions = transitions_result.get("data", {}).get("transitions", [])
                for t in transitions:
                    if t.get("name", "").lower() == transition_name.lower():
                        transition_id = t.get("id")
                        break

                if not transition_id:
                    available = [t.get("name") for t in transitions]
                    return {
                        "error": f"Transition '{transition_name}' not found",
                        "available_transitions": available,
                    }

            return client.transition_issue(issue_key, transition_id)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    # ===== Attachments =====

    @mcp.tool()
    def jira_add_attachment(
        issue_key: str,
        filename: str,
        content_base64: str,
    ) -> dict:
        """
        Add an attachment to a Jira issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            filename: Name for the attachment (e.g., "invoice.pdf")
            content_base64: File content as base64-encoded string

        Returns:
            Dict with attachment info or error

        Example:
            To attach a file, first read it and encode:
            content_base64 = base64.b64encode(file_bytes).decode()
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.add_attachment(issue_key, filename, content_base64)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_list_attachments(issue_key: str) -> dict:
        """
        List attachments on a Jira issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            Dict with list of attachments (id, filename, size, author)
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.list_attachments(issue_key)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    # ===== Users =====

    @mcp.tool()
    def jira_find_user(
        query: str,
        max_results: int = 10,
    ) -> dict:
        """
        Find Jira users by email or display name.

        Use this to get the accountId needed for assigning issues.

        Args:
            query: Search query (email address or name)
            max_results: Maximum results (1-50, default 10)

        Returns:
            Dict with list of matching users (accountId, displayName, emailAddress)
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.find_user(query, max_results)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_get_myself() -> dict:
        """
        Get the currently authenticated Jira user.

        Returns:
            Dict with user info (accountId, displayName, emailAddress)
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.get_myself()
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    # ===== Worklogs =====

    @mcp.tool()
    def jira_add_worklog(
        issue_key: str,
        time_spent: str,
        comment: str | None = None,
    ) -> dict:
        """
        Log time spent on a Jira issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")
            time_spent: Duration in Jira format (e.g., "1h 30m", "2d", "45m")
            comment: Optional work description

        Returns:
            Dict with worklog info or error
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.add_worklog(issue_key, time_spent, comment)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    @mcp.tool()
    def jira_list_worklogs(issue_key: str) -> dict:
        """
        List worklogs for a Jira issue.

        Args:
            issue_key: Issue key (e.g., "PROJ-123")

        Returns:
            Dict with list of worklogs
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.list_worklogs(issue_key)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}

    # ===== Projects =====

    @mcp.tool()
    def jira_list_projects(max_results: int = 50) -> dict:
        """
        List accessible Jira projects.

        Args:
            max_results: Maximum results (1-100, default 50)

        Returns:
            Dict with list of projects (key, name, projectTypeKey)
        """
        client = _get_client()
        if isinstance(client, dict):
            return client
        try:
            return client.list_projects(max_results)
        except httpx.TimeoutException:
            return {"error": "Request timed out"}
        except httpx.RequestError as e:
            return {"error": f"Network error: {e}"}
