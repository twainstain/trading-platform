"""Gmail alert backend.

Sends emails via Gmail SMTP. Requires:
  - GMAIL_ADDRESS: Your Gmail address
  - GMAIL_APP_PASSWORD: App password (not your regular password)
  - GMAIL_RECIPIENT: Where to send alerts
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


class GmailAlert:
    """Send alerts via Gmail SMTP."""

    def __init__(
        self,
        address: str | None = None,
        app_password: str | None = None,
        recipient: str | None = None,
        timeout: float = 15.0,
        subject_prefix: str = "[Trading]",
    ) -> None:
        self.address = address or os.environ.get("GMAIL_ADDRESS", "")
        self.app_password = app_password or os.environ.get("GMAIL_APP_PASSWORD", "")
        self.recipient = recipient or os.environ.get("GMAIL_RECIPIENT", "")
        self.timeout = timeout
        self.subject_prefix = subject_prefix

    @property
    def name(self) -> str:
        return "gmail"

    @property
    def configured(self) -> bool:
        return bool(self.address and self.app_password and self.recipient)

    def send(self, event_type: str, message: str, details: dict | None = None,
             html_body: str | None = None) -> bool:
        if not self.configured:
            logger.debug("Gmail not configured — skipping alert")
            return False

        subject = f"{self.subject_prefix} {event_type.replace('_', ' ').title()}"

        if html_body is None:
            html_body = f"<h3>{event_type.replace('_', ' ').title()}</h3>"
            html_body += f"<pre>{message}</pre>"
            if details:
                html_body += "<table border='1' cellpadding='4' cellspacing='0'>"
                for key, val in details.items():
                    html_body += f"<tr><td><b>{key}</b></td><td>{val}</td></tr>"
                html_body += "</table>"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.address
        msg["To"] = self.recipient
        msg.attach(MIMEText(message, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=self.timeout) as server:
                server.starttls()
                server.login(self.address, self.app_password)
                server.sendmail(self.address, [self.recipient], msg.as_string())
            return True
        except Exception as exc:
            logger.error("Gmail send failed: %s", exc)
            return False
