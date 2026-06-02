from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from src.config import required_env, required_int
from src.exceptions import DomainError
from src.interfaces.email_sender import IEmailSender

logger = logging.getLogger(__name__)


class EmailError(DomainError):
    """Raised when an email could not be delivered. Handled by the global DomainError handler."""

    status_code = 502


class SmtpEmailSender(IEmailSender):
    """Sends plain-text email over SMTP using the stdlib. All connection details
    come from the environment — never hardcoded. Port 465 uses implicit SSL;
    any other port uses STARTTLS (the common case for 587)."""

    def send(self, to: str, subject: str, body: str) -> None:
        host = required_env("SMTP_HOST")
        port = required_int("SMTP_PORT")
        user = required_env("SMTP_USER")
        password = required_env("SMTP_PASSWORD")
        sender = required_env("SMTP_FROM")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = to
        message.set_content(body)

        context = ssl.create_default_context()
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as server:
                    server.login(user, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.starttls(context=context)
                    server.login(user, password)
                    server.send_message(message)
        except Exception as exc:
            logger.exception("Failed to send email to %s", to)
            raise EmailError("Could not send the email. Try again later.") from exc


def get_email_sender() -> IEmailSender:
    return SmtpEmailSender()
