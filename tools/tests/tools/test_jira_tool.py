"""
Tests for Jira tool.

Covers:
- _JiraClient methods (issues, attachments, users, worklogs, projects)
- Error handling (API errors, timeout, network errors)
- Credential retrieval (CredentialStoreAdapter vs env var)
- All 12 MCP tool functions
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastmcp import FastMCP

from aden_tools.tools.jira_tool.jira_tool import (
    _JiraClient,
    register_tools,
)


# --- _JiraClient tests ---


class TestJiraClient:
    def setup_method(self):
        self.client = _JiraClient(
            "https://test.atlassian.net",
            "user@example.com",
            "test_api_token"
        )

    def test_headers_cloud(self):
        headers = self.client._headers
        assert "Basic" in headers["Authorization"]
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"
        # Verify base64 encoding of email:token
        expected_auth = base64.b64encode(b"user@example.com:test_api_token").decode()
        assert headers["Authorization"] == f"Basic {expected_auth}"

    def test_headers_server_pat(self):
        client = _JiraClient("https://jira.example.com", None, "server_pat")
        headers = client._headers
        assert headers["Authorization"] == "Bearer server_pat"

    def test_multipart_headers(self):
        headers = self.client._multipart_headers()
        assert "X-Atlassian-Token" in headers
        assert headers["X-Atlassian-Token"] == "no-check"
        assert "Content-Type" not in headers  # multipart sets its own

    def test_handle_response_success(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"id": "PROJ-1", "key": "PROJ-1"}
        result = self.client._handle_response(response)
        assert result["success"] is True
        assert result["data"]["key"] == "PROJ-1"

    def test_handle_response_401(self):
        response = MagicMock()
        response.status_code = 401
        result = self.client._handle_response(response)
        assert "error" in result
        assert "credentials" in result["error"]

    def test_handle_response_403(self):
        response = MagicMock()
        response.status_code = 403
        result = self.client._handle_response(response)
        assert "error" in result
        assert "Forbidden" in result["error"]

    def test_handle_response_404(self):
        response = MagicMock()
        response.status_code = 404
        result = self.client._handle_response(response)
        assert "error" in result
        assert "not found" in result["error"]

    def test_handle_response_429(self):
        response = MagicMock()
        response.status_code = 429
        result = self.client._handle_response(response)
        assert "error" in result
        assert "Rate limit" in result["error"]

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_create_issue(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "10001",
            "key": "PROJ-1",
            "self": "https://test.atlassian.net/rest/api/3/issue/10001",
        }
        mock_post.return_value = mock_response

        result = self.client.create_issue(
            "PROJ", "Task", "Test summary", description="Test description"
        )

        mock_post.assert_called_once()
        assert result["success"] is True
        assert result["data"]["key"] == "PROJ-1"

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_get_issue(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "key": "PROJ-1",
            "fields": {"summary": "Test issue"},
        }
        mock_get.return_value = mock_response

        result = self.client.get_issue("PROJ-1")

        assert result["success"] is True
        assert result["data"]["key"] == "PROJ-1"

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.put")
    def test_update_issue(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_put.return_value = mock_response

        result = self.client.update_issue("PROJ-1", summary="Updated summary")

        assert result["success"] is True
        assert result["issue_key"] == "PROJ-1"

    def test_update_issue_no_fields(self):
        result = self.client.update_issue("PROJ-1")
        assert "error" in result
        assert "No fields" in result["error"]

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_search_issues(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total": 2,
            "issues": [{"key": "PROJ-1"}, {"key": "PROJ-2"}],
        }
        mock_post.return_value = mock_response

        result = self.client.search_issues("project = PROJ")

        assert result["success"] is True
        assert len(result["data"]["issues"]) == 2

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_get_transitions(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transitions": [
                {"id": "11", "name": "To Do"},
                {"id": "21", "name": "In Progress"},
                {"id": "31", "name": "Done"},
            ]
        }
        mock_get.return_value = mock_response

        result = self.client.get_transitions("PROJ-1")

        assert result["success"] is True
        assert len(result["data"]["transitions"]) == 3

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_transition_issue(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        result = self.client.transition_issue("PROJ-1", "21")

        assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_add_attachment(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "10001", "filename": "test.pdf"}
        ]
        mock_post.return_value = mock_response

        content_b64 = base64.b64encode(b"test content").decode()
        result = self.client.add_attachment("PROJ-1", "test.pdf", content_b64)

        assert result["success"] is True

    def test_add_attachment_invalid_base64(self):
        result = self.client.add_attachment("PROJ-1", "test.pdf", "not_valid_base64!!!")
        assert "error" in result
        assert "Invalid base64" in result["error"]

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_find_user(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"accountId": "abc123", "displayName": "John Doe", "emailAddress": "john@example.com"}
        ]
        mock_get.return_value = mock_response

        result = self.client.find_user("john@example.com")

        assert result["success"] is True
        assert len(result["data"]) == 1

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_get_myself(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "accountId": "xyz789",
            "displayName": "Test User",
        }
        mock_get.return_value = mock_response

        result = self.client.get_myself()

        assert result["success"] is True
        assert result["data"]["accountId"] == "xyz789"

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_add_worklog(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "10001",
            "timeSpent": "2h 30m",
        }
        mock_post.return_value = mock_response

        result = self.client.add_worklog("PROJ-1", "2h 30m", comment="Fixed bug")

        assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_list_worklogs(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "worklogs": [{"id": "10001", "timeSpent": "1h"}]
        }
        mock_get.return_value = mock_response

        result = self.client.list_worklogs("PROJ-1")

        assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_list_projects(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "values": [
                {"key": "PROJ", "name": "My Project"},
                {"key": "ENG", "name": "Engineering"},
            ]
        }
        mock_get.return_value = mock_response

        result = self.client.list_projects()

        assert result["success"] is True


# --- Credential retrieval tests ---


class TestCredentialRetrieval:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    def test_no_credentials_returns_error(self, mcp):
        """When no credentials are configured, tools return helpful error."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("os.getenv", return_value=None):
                register_tools(mcp, credentials=None)
                create_issue = mcp._tool_manager._tools["jira_create_issue"].fn

                result = create_issue(
                    project_key="PROJ",
                    issue_type="Task",
                    summary="Test"
                )

                assert "error" in result
                assert "not configured" in result["error"]

    def test_env_var_credentials(self, mcp):
        """Token from env vars is used."""
        env_vars = {
            "JIRA_BASE_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "user@test.com",
            "JIRA_API_TOKEN": "test_token",
        }
        with patch("os.getenv", side_effect=lambda k, d=None: env_vars.get(k, d)):
            with patch("aden_tools.tools.jira_tool.jira_tool.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"values": []}
                mock_get.return_value = mock_response

                register_tools(mcp, credentials=None)
                list_projects = mcp._tool_manager._tools["jira_list_projects"].fn

                list_projects()

                call_headers = mock_get.call_args.kwargs["headers"]
                assert "Basic" in call_headers["Authorization"]

    def test_credential_store(self, mcp):
        """Credentials from CredentialStoreAdapter are used."""
        mock_credentials = MagicMock()
        mock_credentials.get.side_effect = lambda k: {
            "jira_base_url": "https://store.atlassian.net",
            "jira_email": "store@test.com",
            "jira_api_token": "store_token",
        }.get(k)

        with patch("aden_tools.tools.jira_tool.jira_tool.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"values": []}
            mock_get.return_value = mock_response

            register_tools(mcp, credentials=mock_credentials)
            list_projects = mcp._tool_manager._tools["jira_list_projects"].fn

            list_projects()

            mock_credentials.get.assert_any_call("jira_base_url")


# --- MCP Tool function tests ---


class TestJiraCreateIssue:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_create_issue_success(self, mock_post, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"key": "PROJ-1"}
        mock_post.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            create_issue = mcp._tool_manager._tools["jira_create_issue"].fn

            result = create_issue(project_key="PROJ", issue_type="Task", summary="Test")

            assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_create_issue_timeout(self, mock_post, mcp):
        mock_post.side_effect = httpx.TimeoutException("Timeout")

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            create_issue = mcp._tool_manager._tools["jira_create_issue"].fn

            result = create_issue(project_key="PROJ", issue_type="Task", summary="Test")

            assert "error" in result
            assert "timed out" in result["error"]


class TestJiraSearchIssues:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_search_issues_success(self, mock_post, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issues": [], "total": 0}
        mock_post.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            search = mcp._tool_manager._tools["jira_search_issues"].fn

            result = search(jql="project = PROJ")

            assert result["success"] is True


class TestJiraTransitionIssue:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    def test_transition_no_params(self, mcp):
        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            transition = mcp._tool_manager._tools["jira_transition_issue"].fn

            result = transition(issue_key="PROJ-1")

            assert "error" in result

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_transition_by_name(self, mock_post, mock_get, mcp):
        # Mock get transitions
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "transitions": [{"id": "21", "name": "In Progress"}]
        }
        mock_get.return_value = mock_get_response

        # Mock transition
        mock_post_response = MagicMock()
        mock_post_response.status_code = 204
        mock_post.return_value = mock_post_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            transition = mcp._tool_manager._tools["jira_transition_issue"].fn

            result = transition(issue_key="PROJ-1", transition_name="In Progress")

            assert result["success"] is True


class TestJiraAttachments:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_add_attachment_success(self, mock_post, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"filename": "test.pdf"}]
        mock_post.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            add_att = mcp._tool_manager._tools["jira_add_attachment"].fn

            content = base64.b64encode(b"test").decode()
            result = add_att(issue_key="PROJ-1", filename="test.pdf", content_base64=content)

            assert result["success"] is True


class TestJiraUsers:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_find_user_success(self, mock_get, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"accountId": "123", "displayName": "Test"}]
        mock_get.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            find_user = mcp._tool_manager._tools["jira_find_user"].fn

            result = find_user(query="test@example.com")

            assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_get_myself_success(self, mock_get, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"accountId": "me123"}
        mock_get.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            get_myself = mcp._tool_manager._tools["jira_get_myself"].fn

            result = get_myself()

            assert result["success"] is True


class TestJiraWorklogs:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.post")
    def test_add_worklog_success(self, mock_post, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "10001", "timeSpent": "2h"}
        mock_post.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            add_worklog = mcp._tool_manager._tools["jira_add_worklog"].fn

            result = add_worklog(issue_key="PROJ-1", time_spent="2h")

            assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_list_worklogs_success(self, mock_get, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"worklogs": []}
        mock_get.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            list_worklogs = mcp._tool_manager._tools["jira_list_worklogs"].fn

            result = list_worklogs(issue_key="PROJ-1")

            assert result["success"] is True


class TestJiraProjects:
    @pytest.fixture
    def mcp(self):
        return FastMCP("test-server")

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_list_projects_success(self, mock_get, mcp):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"values": [{"key": "PROJ"}]}
        mock_get.return_value = mock_response

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            list_projects = mcp._tool_manager._tools["jira_list_projects"].fn

            result = list_projects()

            assert result["success"] is True

    @patch("aden_tools.tools.jira_tool.jira_tool.httpx.get")
    def test_list_projects_network_error(self, mock_get, mcp):
        mock_get.side_effect = httpx.RequestError("Network error")

        env = {"JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "t"}
        with patch("os.getenv", side_effect=lambda k, d=None: env.get(k, d)):
            register_tools(mcp, credentials=None)
            list_projects = mcp._tool_manager._tools["jira_list_projects"].fn

            result = list_projects()

            assert "error" in result
            assert "Network error" in result["error"]
