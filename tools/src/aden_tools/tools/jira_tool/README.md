# Jira Tool

Manage Jira issues, attachments, users, and worklogs via Jira REST API v3.

## Setup

### Jira Cloud
```bash
export JIRA_BASE_URL=https://yourcompany.atlassian.net
export JIRA_EMAIL=user@company.com
export JIRA_API_TOKEN=your_api_token
```

Get an API token at: https://id.atlassian.com/manage-profile/security/api-tokens

### Jira Server/Data Center
```bash
export JIRA_BASE_URL=https://jira.yourcompany.com
export JIRA_PAT=your_personal_access_token
```

## Available Tools

| Tool | Description |
|------|-------------|
| `jira_create_issue` | Create issue with project, type, summary, description |
| `jira_get_issue` | Get issue by key (PROJ-123) |
| `jira_update_issue` | Update summary, description, assignee, priority |
| `jira_search_issues` | Search with JQL |
| `jira_transition_issue` | Move issue to new status |
| `jira_add_attachment` | Attach file (base64) to issue |
| `jira_list_attachments` | List attachments on issue |
| `jira_find_user` | Find user by email/name → get accountId |
| `jira_get_myself` | Get authenticated user |
| `jira_add_worklog` | Log time spent |
| `jira_list_worklogs` | List worklogs |
| `jira_list_projects` | List accessible projects |

## Example Usage

```python
# Create an issue
jira_create_issue(
    project_key="PROJ",
    issue_type="Task",
    summary="Implement OAuth flow",
    description="Add OAuth2 support for third-party integrations",
    priority="High"
)

# Find user and assign
user = jira_find_user("john@company.com")
account_id = user["data"][0]["accountId"]
jira_update_issue("PROJ-123", assignee_account_id=account_id)

# Transition to In Progress
jira_transition_issue("PROJ-123", transition_name="In Progress")

# Log work
jira_add_worklog("PROJ-123", "2h 30m", "Initial implementation")
```
