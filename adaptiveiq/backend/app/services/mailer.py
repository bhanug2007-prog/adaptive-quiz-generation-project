"""Sends account emails (verification links) over SMTP.

Without SMTP settings (development), the message is written to the backend log instead, and the last
few messages are kept in memory (`outbox`) so tests can read the link. Production refuses to start
without SMTP when email verification is required (see core/config.py)."""
import logging
import smtplib
import threading
from collections import deque
from email.message import EmailMessage

from app.core.config import Settings

log = logging.getLogger("adaptiveiq.mail")


class Mailer:
    def __init__(self, s: Settings):
        self.s = s
        self.outbox: deque = deque(maxlen=50)

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.s.smtp_configured:
            if self.s.environment == "production":
                # Never print links (they work like passwords) into production logs.
                log.error("SMTP is not configured, so the email to %s (%s) was not sent.", to, subject)
                return
            self.outbox.append({"to": to, "subject": subject, "body": body})
            log.warning("SMTP is not configured, so this email was not sent. To %s | %s\n%s", to, subject, body)
            return
        threading.Thread(target=self._smtp, args=(to, subject, body), daemon=True).start()

    def send_password_reset_smtp(self, to: str, full_name: str, reset_link: str, expires_minutes: int) -> None:
        """Send a password reset email over SMTP without ever logging the token, link, or recipient."""
        if not self.s.smtp_configured:
            return
        subject = "Reset your AdaptiveIQ password"
        body = (
            f"Hello {full_name},\n\n"
            f"We received a request to reset your AdaptiveIQ password. Open this link to choose a new password:\n"
            f"{reset_link}\n\n"
            f"This link expires in {expires_minutes} minutes and can only be used once.\n"
            f"If you did not request a password reset, you can ignore this email.\n"
        )
        threading.Thread(target=self._smtp_silent, args=(to, subject, body), daemon=True).start()

    def _smtp(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.smtp_from, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=20) as smtp:
                if self.s.smtp_starttls:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(msg)
        except Exception:
            log.exception("Could not send email to %s", to)

    def _smtp_silent(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.smtp_from, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=20) as smtp:
                if self.s.smtp_starttls:
                    smtp.starttls()
                if self.s.smtp_user:
                    smtp.login(self.s.smtp_user, self.s.smtp_password)
                smtp.send_message(msg)
        except Exception:
            # Never log recipient, token, or reset link on failure.
            log.error("Could not send password reset email via SMTP.")
