"""Reporter Node: Sends email digest of important issues."""

import logging
from datetime import datetime, timezone
from framework.graph import NodeSpec, NodeContext, NodeResult, NodeProtocol
from ..config import settings
from ..models import get_db

logger = logging.getLogger(__name__)


class ReporterNode(NodeProtocol):
    """
    Reporter Node implementation.
    Compiles high-value issues into a categorized HTML digest and sends via email.
    Tracks reported issues to prevent duplicates across runs.
    """
    async def execute(self, ctx: NodeContext) -> NodeResult:
        logger.info("Starting ReporterNode execution")

        # 1. Inputs
        analyzed_issues = ctx.memory.read("analyzed_issues") or []
        notification_email = ctx.memory.read("notification_email")

        if not analyzed_issues:
            logger.info("No analyzed issues to report.")
            return NodeResult(success=True, output={"digest_sent": False})

        if not notification_email:
            logger.warning("No notification_email provided. Skipping email.")
            return NodeResult(success=True, output={"digest_sent": False})

        # 2. Filter out already-reported issues
        logger.info(f"Filtering {len(analyzed_issues)} issues against reported history...")
        db = get_db()
        reported_numbers = db.get_reported_issue_numbers(
            settings.github_repo_owner,
            settings.github_repo_name
        )

        new_issues = [
            issue for issue in analyzed_issues
            if issue.get("number") not in reported_numbers
        ]

        if not new_issues:
            logger.info(f"All {len(analyzed_issues)} issues were already reported. Skipping digest.")
            return NodeResult(success=True, output={"digest_sent": False})

        logger.info(f"Found {len(new_issues)} new issues to report (filtered from {len(analyzed_issues)})")

        # 3. Categorize
        # 🐛 Bugs: ["bug", "regression", "crash"]
        # ✨ Enhancements: ["enhancement", "feature", "feature-request"]
        # 🔌 Integrations: ["integration", "plugin", "extension"]
        # 🔒 Security: ["security", "vulnerability", "exploit"]
        # 📚 Documentation: ["documentation", "docs", "readme"]
        
        categories = {
            "🐛 Bugs": [],
            "✨ Enhancements": [],
            "🔌 Integrations": [],
            "🔒 Security": [],
            "📚 Documentation": [],
            "🎯 Other": []
        }

        for issue in new_issues:
            labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
            # Also check title/summary for keywords if labels missing? strict for now.

            assigned = False
            for label in labels:
                if any(k in label for k in ["bug", "regression", "crash"]):
                    categories["🐛 Bugs"].append(issue)
                    assigned = True
                    break
                elif any(k in label for k in ["enhancement", "feature"]):
                    categories["✨ Enhancements"].append(issue)
                    assigned = True
                    break
                elif any(k in label for k in ["integration", "plugin", "extension"]):
                    categories["🔌 Integrations"].append(issue)
                    assigned = True
                    break
                elif any(k in label for k in ["security", "vulnerability"]):
                    categories["🔒 Security"].append(issue)
                    assigned = True
                    break
                elif any(k in label for k in ["documentation", "docs"]):
                    categories["📚 Documentation"].append(issue)
                    assigned = True
                    break

            if not assigned:
                categories["🎯 Other"].append(issue)

        # 4. Sort by Impact (Desc)
        for cat in categories:
            categories[cat].sort(key=lambda x: x.get("impact_score", 0), reverse=True)

        # 5. Build HTML
        count = len(new_issues)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        html_parts = [
            '<html>',
            '<head><style>',
            '.issue { margin: 15px 0; padding: 10px; border-left: 4px solid #ddd; font-family: sans-serif; }',
            '.severity-critical { background: #fee; border-left-color: #d00; }',
            '.severity-high { background: #fef0e0; border-left-color: #f90; }',
            '.severity-medium { background: #fef5e0; border-left-color: #fc0; }',
            '.severity-low { background: #f0f0f0; border-left-color: #999; }',
            '.badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 11px; margin-right: 5px; }',
            '.badge-critical { background: #d00; color: white; }',
            '.badge-high { background: #f90; color: white; }',
            '.badge-medium { background: #fc0; color: black; }',
            '.badge-low { background: #999; color: white; }',
            '.meta { font-size: 12px; color: #666; margin-top: 5px; }',
            'h2, h3 { font-family: sans-serif; }',
            '</style></head>',
            '<body>',
            f'<h2>GitHub Issue Digest: {count} New Issues Requiring Attention</h2>',
            f'<p>Generated at {timestamp}</p>'
        ]

        for cat_name, items in categories.items():
            if not items:
                continue

            html_parts.append(f'<h3>{cat_name} ({len(items)})</h3>')

            for item in items:
                severity = item.get("severity", "Low")
                severity_cls = severity.lower().replace(" ", "-") if severity else "low"

                # Badge mapping
                badge_cls = "badge-low"
                if "critical" in severity_cls: badge_cls = "badge-critical"
                elif "high" in severity_cls: badge_cls = "badge-high"
                elif "medium" in severity_cls: badge_cls = "badge-medium"

                html_parts.append(f'<div class="issue severity-{severity_cls}">')
                html_parts.append('<div>')
                html_parts.append(f'<span class="badge {badge_cls}">{severity.upper() if severity else "LOW"}</span>')
                html_parts.append(f'<a href="{item.get("url")}">#{ item.get("number") }: {item.get("title")}</a>')
                html_parts.append('</div>')
                html_parts.append('<div class="meta">')
                html_parts.append(f'<strong>Impact: {item.get("impact_score")}/100</strong> | Novelty: {item.get("novelty_score")}/10')
                html_parts.append('</div>')
                html_parts.append(f'<div><strong>Summary:</strong> {item.get("summary")}</div>')

                if item.get("reasoning"):
                     html_parts.append(f'<div><strong>Analysis:</strong> {item.get("reasoning")}</div>')

                html_parts.append('</div>')

        html_parts.append('</body></html>')
        html_body = "\n".join(html_parts)

        # 6. Send Email
        subject = f"GitHub Issue Digest: {count} New Issues - {datetime.now().strftime('%Y-%m-%d')}"

        logger.info(f"Sending email to {notification_email}...")

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            if not settings.smtp_host or not settings.smtp_password:
                logger.error("SMTP credentials not configured in settings. Cannot send email.")
                logger.error(f"  SMTP_HOST: {settings.smtp_host}")
                logger.error(f"  SMTP_USERNAME: {settings.smtp_username}")
                logger.error(f"  NOTIFICATION_EMAIL: {notification_email}")
                return NodeResult(success=True, output={"digest_sent": False})

            msg = MIMEMultipart("alternative")
            msg["From"] = settings.smtp_username or notification_email
            msg["To"] = notification_email
            msg["Subject"] = subject
            msg.attach(MIMEText(html_body, "html"))

            logger.info(f"Connecting to SMTP {settings.smtp_host}:{settings.smtp_port}...")
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                logger.info(f"Authenticating as {settings.smtp_username}...")
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)

            logger.info("Email sent successfully via SMTP.")

            # 7. Mark all sent issues as reported
            logger.info(f"Marking {len(new_issues)} issues as reported in database...")
            db = get_db()
            for issue in new_issues:
                db.mark_issue_reported(
                    owner=settings.github_repo_owner,
                    repo=settings.github_repo_name,
                    issue_number=issue.get("number"),
                    issue_title=issue.get("title"),
                    impact_score=issue.get("impact_score"),
                    severity=issue.get("severity")
                )

            logger.info("Successfully marked issues as reported.")
            return NodeResult(success=True, output={"digest_sent": True})

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed: {e}")
            logger.error(f"  Check SMTP_USERNAME ({settings.smtp_username}) and SMTP_PASSWORD")
            return NodeResult(success=True, output={"digest_sent": False})
        except smtplib.SMTPException as e:
            logger.error(f"SMTP Error: {e}")
            return NodeResult(success=True, output={"digest_sent": False})
        except Exception as e:
            logger.error(f"Failed to send email: {e}", exc_info=True)
            return NodeResult(success=True, output={"digest_sent": False})

reporter_node = NodeSpec(
    id="reporter",
    name="Reporter",
    description="Compile high-value issues into a categorized HTML digest and send via email.",
    node_type="function",
    function="examples.templates.GitFlexi_Agent.nodes.reporter.ReporterNode",
    input_keys=["analyzed_issues", "notification_email"],
    output_keys=["digest_sent"],
    client_facing=False
)
