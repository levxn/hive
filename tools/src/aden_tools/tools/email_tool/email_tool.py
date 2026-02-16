"""
Email Tool - Send and reply to emails using multiple providers.

Supports:
- Gmail (GOOGLE_ACCESS_TOKEN, via Aden OAuth2)
- Resend (RESEND_API_KEY)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

import httpx
import resend
from fastmcp import FastMCP

if TYPE_CHECKING:
    from aden_tools.credentials import CredentialStoreAdapter


class EmailClient:
    """Standalone email client for direct usage (e.g. by agents)."""

    def __init__(self, credentials: dict | None = None):
        """
        Initialize EmailClient.

        Args:
            credentials: Optional dictionary or CredentialStoreAdapter-like object
                       containing credentials.
        """
        self._credentials = credentials
        self._use_env_vars = credentials is None

        # These are now accessed dynamically via properties
        self._resend_api_key = None
        self._gmail_access_token = None
        self._smtp_config = None

        # Backward compatibility for direct dict usage (if users passed a dict with keys)
        if isinstance(credentials, dict):
            self._resend_api_key = credentials.get("resend")
            self._gmail_access_token = credentials.get("google")
            self._smtp_config = credentials.get("smtp")

    @property
    def resend_api_key(self) -> str | None:
        if self._use_env_vars:
            return os.getenv("RESEND_API_KEY")

        # Check explicit dict value first
        if self._resend_api_key:
            return self._resend_api_key

        # Try dynamic lookup from adapter
        if self._credentials and hasattr(self._credentials, "get"):
            try:
                return self._credentials.get("resend")
            except Exception:
                pass
        return None

    @property
    def gmail_access_token(self) -> str | None:
        if self._use_env_vars:
            return os.getenv("GOOGLE_ACCESS_TOKEN")

        if self._gmail_access_token:
            return self._gmail_access_token

        if self._credentials and hasattr(self._credentials, "get"):
            try:
                return self._credentials.get("google")
            except Exception:
                pass
        return None

    @property
    def smtp_config(self) -> dict | None:
        if self._use_env_vars:
            host = os.getenv("SMTP_HOST")
            port = int(os.getenv("SMTP_PORT", "587"))
            username = os.getenv("SMTP_USERNAME")
            password = os.getenv("SMTP_PASSWORD")
            if host and password:
                return {
                    "host": host,
                    "port": port,
                    "username": username,
                    "password": password,
                }
            return None

        if self._smtp_config:
            return self._smtp_config

        if self._credentials and hasattr(self._credentials, "get"):
            try:
                val = self._credentials.get("smtp")
                if val and isinstance(val, dict):
                    return val
            except Exception:
                pass
        return None

    def _resolve_from_email(self, from_email: str | None) -> str | None:
        if from_email:
            return from_email
        smtp_user = self.smtp_config.get("username") if self.smtp_config else None
        return os.getenv("EMAIL_FROM") or smtp_user

    def _send_via_smtp(
        self,
        to: list[str],
        subject: str,
        html: str,
        from_email: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Send email using SMTP (e.g. Gmail App Password)."""
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        if not self.smtp_config["host"] or not self.smtp_config["password"]:
            return {"error": "SMTP server/password not configured"}

        msg = MIMEMultipart("alternative")
        msg["From"] = from_email
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg.attach(MIMEText(html, "html"))

        try:
            with smtplib.SMTP(self.smtp_config["host"], self.smtp_config["port"]) as server:
                server.starttls()
                server.login(self.smtp_config["username"], self.smtp_config["password"])
                server.send_message(msg)

            return {"success": True, "provider": "smtp", "to": to, "subject": subject}
        except Exception as e:
            return {"error": f"SMTP send failed: {e}"}

    def _send_via_resend(
        self,
        api_key: str,
        to: list[str],
        subject: str,
        html: str,
        from_email: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Send email using Resend API."""
        resend.api_key = api_key
        try:
            payload: dict = {
                "from": from_email,
                "to": to,
                "subject": subject,
                "html": html,
            }
            if cc:
                payload["cc"] = cc
            if bcc:
                payload["bcc"] = bcc
            email = resend.Emails.send(payload)
            return {
                "success": True,
                "provider": "resend",
                "id": email.get("id", ""),
                "to": to,
                "subject": subject,
            }
        except resend.exceptions.ResendError as e:
            return {"error": f"Resend API error: {e}"}

    def _send_via_gmail(
        self,
        access_token: str,
        to: list[str],
        subject: str,
        html: str,
        from_email: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> dict:
        """Send email using Gmail API."""
        import base64
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if from_email:
            msg["From"] = from_email
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        response = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=30.0,
        )

        if response.status_code == 401:
            return {
                "error": "Gmail token expired or invalid",
                "help": "Re-authorize via hive.adenhq.com",
            }
        if response.status_code != 200:
            return {
                "error": f"Gmail API error (HTTP {response.status_code}): {response.text}",
            }

        data = response.json()
        return {
            "success": True,
            "provider": "gmail",
            "id": data.get("id", ""),
            "to": to,
            "subject": subject,
        }

    def _normalize_recipients(self, value: str | list[str] | None) -> list[str] | None:
        """Normalize a recipient value to a list or None."""
        if value is None:
            return None
        if isinstance(value, str):
            return [value] if value.strip() else None
        filtered = [v for v in value if isinstance(v, str) and v.strip()]
        return filtered if filtered else None

    def send_email(
        self,
        to: str | list[str],
        subject: str,
        html: str,
        provider: Literal["resend", "gmail"] = "gmail",
        from_email: str | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict:
        """Core email sending logic."""
        from_email = self._resolve_from_email(from_email)

        to_list = self._normalize_recipients(to)
        if not to_list:
            return {"error": "At least one recipient email is required"}
        if not subject or len(subject) > 998:
            return {"error": "Subject must be 1-998 characters"}
        if not html:
            return {"error": "Email body (html) is required"}

        cc_list = self._normalize_recipients(cc)
        bcc_list = self._normalize_recipients(bcc)

        override_to = os.getenv("EMAIL_OVERRIDE_TO")
        if override_to:
            original_to = to_list
            to_list = [override_to]
            cc_list = None
            bcc_list = None
            subject = f"[TEST -> {', '.join(original_to)}] {subject}"

        # Resend always requires from_email; Gmail defaults to authenticated user.
        if provider == "resend" and not from_email:
            return {
                "error": "Sender email is required",
                "help": "Pass from_email or set EMAIL_FROM environment variable",
            }

        if provider == "gmail":
            credential = self.gmail_access_token
            if not credential:
                return {
                    "error": "Gmail credentials not configured",
                    "help": "Connect Gmail via hive.adenhq.com",
                }
        else:
            credential = self.resend_api_key
            if not credential:
                return {
                    "error": "Resend credentials not configured",
                    "help": "Set RESEND_API_KEY environment variable. "
                    "Get a key at https://resend.com/api-keys",
                }

        try:
            if provider == "gmail":
                return self._send_via_gmail(
                    credential, to_list, subject, html, from_email, cc_list, bcc_list
                )
            return self._send_via_resend(
                credential, to_list, subject, html, from_email, cc_list, bcc_list
            )
        except Exception as e:
            return {"error": f"Email send failed: {e}"}


def register_tools(
    mcp: FastMCP,
    credentials: CredentialStoreAdapter | None = None,
) -> None:
    """Register email tools with the MCP server."""

    # Initialize client (will capture env vars if credentials is None)
    creds_dict = None
    if credentials:
        creds_dict = {
            "resend": credentials.get("resend"),
            "google": credentials.get("google"),
        }

    client = EmailClient(creds_dict)

    @mcp.tool()
    def send_email(
        to: str | list[str],
        subject: str,
        html: str,
        provider: Literal["resend", "gmail"],
        from_email: str | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict:
        """
        Send an email.

        Supports multiple email providers:
        - "gmail": Use Gmail API (requires Gmail OAuth2 via Aden)
        - "resend": Use Resend API (requires RESEND_API_KEY)

        Args:
            to: Recipient email address(es). Single string or list of strings.
            subject: Email subject line (1-998 chars per RFC 2822).
            html: Email body as HTML string.
            provider: Email provider to use ("gmail" or "resend"). Required.
            from_email: Sender email address. Falls back to EMAIL_FROM env var if not provided.
                        Optional for Gmail (defaults to authenticated user's address).
            cc: CC recipient(s). Single string or list of strings. Optional.
            bcc: BCC recipient(s). Single string or list of strings. Optional.

        Returns:
            Dict with send result including provider used and message ID,
            or error dict with "error" and optional "help" keys.
        """
        return client.send_email(
            to=to,
            subject=subject,
            html=html,
            provider=provider,
            from_email=from_email,
            cc=cc,
            bcc=bcc,
        )

    def _fetch_original_message(access_token: str, message_id: str) -> dict:
        """Fetch the original message to extract threading info."""
        response = httpx.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            params={"format": "metadata", "metadataHeaders": ["Message-ID", "Subject", "From"]},
            timeout=30.0,
        )

        if response.status_code == 401:
            return {
                "error": "Gmail token expired or invalid",
                "help": "Re-authorize via hive.adenhq.com",
            }
        if response.status_code == 404:
            return {"error": f"Original message not found: {message_id}"}
        if response.status_code != 200:
            return {
                "error": f"Gmail API error (HTTP {response.status_code}): {response.text}",
            }

        data = response.json()
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        return {
            "thread_id": data.get("threadId"),
            "message_id_header": headers.get("Message-ID", headers.get("Message-Id", "")),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
        }

    @mcp.tool()
    def gmail_reply_email(
        message_id: str,
        html: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict:
        """
        Reply to a Gmail message, keeping it in the same thread.

        Fetches the original message to get threading info (threadId, Message-ID,
        subject, sender), then sends a reply with proper In-Reply-To and References
        headers so it appears as a threaded reply in Gmail.

        Args:
            message_id: The Gmail message ID to reply to.
            html: Reply body as HTML string.
            cc: CC recipient(s). Single string or list of strings. Optional.
            bcc: BCC recipient(s). Single string or list of strings. Optional.

        Returns:
            Dict with send result including reply message ID and threadId,
            or error dict with "error" and optional "help" keys.
        """
        import base64
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        if not message_id or not message_id.strip():
            return {"error": "message_id is required"}
        if not html:
            return {"error": "Reply body (html) is required"}

        credential = client.gmail_access_token
        if not credential:
            return {
                "error": "Gmail credentials not configured",
                "help": "Connect Gmail via hive.adenhq.com",
            }

        # Fetch original message for threading info
        try:
            original = _fetch_original_message(credential, message_id)
        except httpx.HTTPError as e:
            return {"error": f"Failed to fetch original message: {e}"}

        if "error" in original:
            return original

        thread_id = original["thread_id"]
        original_message_id = original["message_id_header"]
        original_subject = original["subject"]
        reply_to_address = original["from"]

        # Build reply subject
        subject = original_subject
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Build MIME message with threading headers
        msg = MIMEMultipart("alternative")
        msg["To"] = reply_to_address
        msg["Subject"] = subject
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        cc_list = client._normalize_recipients(cc)
        bcc_list = client._normalize_recipients(bcc)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        if bcc_list:
            msg["Bcc"] = ", ".join(bcc_list)

        msg.attach(MIMEText(html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        # Testing override
        override_to = os.getenv("EMAIL_OVERRIDE_TO")
        if override_to:
            # Rebuild with overridden recipient
            msg.replace_header("To", override_to)
            if "Cc" in msg:
                del msg["Cc"]
            if "Bcc" in msg:
                del msg["Bcc"]
            msg.replace_header("Subject", f"[TEST -> {reply_to_address}] {subject}")
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        try:
            response = httpx.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={
                    "Authorization": f"Bearer {credential}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw, "threadId": thread_id},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            return {"error": f"Failed to send reply: {e}"}

        if response.status_code == 401:
            return {
                "error": "Gmail token expired or invalid",
                "help": "Re-authorize via hive.adenhq.com",
            }
        if response.status_code != 200:
            return {
                "error": f"Gmail API error (HTTP {response.status_code}): {response.text}",
            }

        data = response.json()
        return {
            "success": True,
            "provider": "gmail",
            "id": data.get("id", ""),
            "threadId": data.get("threadId", ""),
            "to": reply_to_address,
            "subject": subject,
        }
