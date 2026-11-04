"""
Email MIME Builder, Dispatcher, and Anti-Spam Rate Limiter
"""
import base64
import mimetypes
import time
import random
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, Tuple


def build_mime_message(
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    from_email: Optional[str] = None,
    attachment_path: Optional[Path] = None
) -> Dict[str, str]:
    """
    Construct RFC 2822 compliant MIME message with plain text, HTML, and optional PDF attachment.
    Returns: {"raw": urlsafe_b64_encoded_string}
    """
    # Outer container
    message = MIMEMultipart("mixed")
    message["To"] = to_email
    message["Subject"] = subject
    if from_email:
        message["From"] = from_email

    # Alternative container for text + HTML
    msg_body = MIMEMultipart("alternative")
    part_text = MIMEText(text_body, "plain", "utf-8")
    part_html = MIMEText(html_body, "html", "utf-8")
    msg_body.attach(part_text)
    msg_body.attach(part_html)
    message.attach(msg_body)

    # Optional attachment (e.g. resume.pdf)
    if attachment_path and Path(attachment_path).exists():
        att_path = Path(attachment_path)
        content_type, encoding = mimetypes.guess_type(str(att_path))
        if content_type is None or encoding is not None:
            content_type = "application/octet-stream"
        
        main_type, sub_type = content_type.split("/", 1)
        with open(att_path, "rb") as f:
            att_part = MIMEBase(main_type, sub_type)
            att_part.set_payload(f.read())
        
        encoders.encode_base64(att_part)
        display_name = att_path.name
        if "\\" in display_name or "/" in display_name or display_name.lower() in ["resume.pdf", "shreya_yadav_ai\\ml.pdf"]:
            display_name = "Shreya_Yadav_Resume.pdf"
        att_part.add_header(
            "Content-Disposition",
            f'attachment; filename="{display_name}"'
        )
        message.attach(att_part)

    # Base64 encode for Gmail API
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return {"raw": raw}


class EmailDispatcher:
    """Dispatches emails or creates drafts via Gmail API with jitter and rate limiting."""

    def __init__(
        self,
        gmail_service: Any,
        tracker: Any,
        min_jitter: int = 20,
        max_jitter: int = 45,
        max_daily_limit: int = 50,
        verifier: Optional[Any] = None,
        is_dry_run: bool = False
    ):
        self.service = gmail_service
        self.tracker = tracker
        self.min_jitter = min_jitter
        self.max_jitter = max_jitter
        self.max_daily_limit = max_daily_limit
        self.verifier = verifier
        self.is_dry_run = bool(is_dry_run)

    def apply_jitter(self, action_name: str = "operation"):
        """Wait randomized interval to simulate natural human activity."""
        delay = random.uniform(self.min_jitter, self.max_jitter)
        print(f"  ⏳ Anti-spam pause: sleeping {delay:.1f}s before next {action_name}...")
        time.sleep(delay)

    def create_draft(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachment_path: Optional[Path] = None,
        contact_meta: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Create personalized draft in Gmail.
        Returns: (success, message_or_error, draft_id)
        """
        # Suppression check
        if self.tracker.is_suppressed(to_email):
            return (False, f"Skipped: {to_email} is in suppression/opt-out list", None)

        if self.tracker.is_already_contacted(to_email):
            return (False, f"Skipped: {to_email} already contacted/drafted", None)

        # Two-condition security check: Available & Deliverable
        if self.verifier:
            sec_check = self.verifier.security_check(to_email)
            if not sec_check.can_draft:
                if not self.is_dry_run:
                    self.tracker.delete_contact(to_email)
                action_str = "DELETED from queue" if not self.is_dry_run else "[Simulated] WOULD DELETE from queue"
                return (False, f"{action_str}: {sec_check.reason}", None)

        try:
            mime_msg = build_mime_message(
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                attachment_path=attachment_path
            )
            draft_body = {"message": mime_msg}
            res = self.service.users().drafts().create(userId="me", body=draft_body).execute()
            draft_id = res.get("id")

            # Record in persistence tracker
            if not self.is_dry_run:
                meta = contact_meta or {}
                self.tracker.upsert_contact_status(
                    email=to_email,
                    name=meta.get("cleaned_name", ""),
                    company=meta.get("cleaned_company", ""),
                    job_title=meta.get("job_title", ""),
                    status="DRAFTED",
                    template_key=meta.get("template_key"),
                    subject=subject,
                    draft_id=draft_id
                )
                self.tracker.increment_daily_counter("drafts_count")
            return (True, f"Draft created successfully (ID: {draft_id})", draft_id)

        except Exception as e:
            err_msg = str(e)
            if not self.is_dry_run:
                self.tracker.upsert_contact_status(
                    email=to_email,
                    status="FAILED",
                    error_message=err_msg
                )
                self.tracker.increment_daily_counter("failed_count")
            return (False, f"Failed to create draft: {err_msg}", None)

    def delete_draft(self, draft_id: str) -> bool:
        """Permanently delete a draft from Gmail."""
        if not draft_id or str(draft_id).startswith("mock_draft"):
            return True
        if self.is_dry_run:
            return True
        try:
            self.service.users().drafts().delete(userId="me", id=draft_id).execute()
            return True
        except Exception:
            return False

    def send_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str,
        attachment_path: Optional[Path] = None,
        contact_meta: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Send single personalized email directly via Gmail API.
        Returns: (success, message_or_error, message_id)
        """
        # Daily limit check (enforced only during live dispatch)
        sent_today = self.tracker.get_daily_count("sent_count")
        if not self.is_dry_run and sent_today >= self.max_daily_limit:
            return (False, f"Daily limit reached ({sent_today}/{self.max_daily_limit}). Aborting send.", None)

        # Suppression check
        if self.tracker.is_suppressed(to_email):
            return (False, f"Skipped: {to_email} is in suppression/opt-out list", None)

        if self.tracker.is_already_contacted(to_email):
            return (False, f"Skipped: {to_email} already contacted", None)

        # Two-condition security check: Available & Deliverable
        if self.verifier:
            sec_check = self.verifier.security_check(to_email)
            if not sec_check.can_draft:
                if not self.is_dry_run:
                    self.tracker.delete_contact(to_email)
                action_str = "DELETED from queue" if not self.is_dry_run else "[Simulated] WOULD DELETE from queue"
                return (False, f"{action_str}: {sec_check.reason}", None)

        try:
            mime_msg = build_mime_message(
                to_email=to_email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                attachment_path=attachment_path
            )
            res = self.service.users().messages().send(userId="me", body=mime_msg).execute()
            message_id = res.get("id")

            # Record in persistence tracker
            if not self.is_dry_run:
                meta = contact_meta or {}
                self.tracker.upsert_contact_status(
                    email=to_email,
                    name=meta.get("cleaned_name", ""),
                    company=meta.get("cleaned_company", ""),
                    job_title=meta.get("job_title", ""),
                    status="SENT",
                    template_key=meta.get("template_key"),
                    subject=subject,
                    message_id=message_id
                )
                self.tracker.increment_daily_counter("sent_count")
            return (True, f"Email sent successfully (Message ID: {message_id})", message_id)

        except Exception as e:
            err_msg = str(e)
            if not self.is_dry_run:
                self.tracker.upsert_contact_status(
                    email=to_email,
                    status="FAILED",
                    error_message=err_msg
                )
                self.tracker.increment_daily_counter("failed_count")
            return (False, f"Failed to send email: {err_msg}", None)
