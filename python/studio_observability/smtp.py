"""Bounded SMTP notification adapter for the reference deployment profile."""

from __future__ import annotations

import smtplib
from collections.abc import Callable, Sequence
from email.message import EmailMessage

from .notifications import NotificationIntent


class SmtpNotificationError(RuntimeError):
    """Raised when an SMTP notification cannot be delivered safely."""


class SmtpNotificationSink:
    """Send plain-text intents through an authenticated external SMTP relay.

    Authentication is deliberately delegated to the injected factory/configured
    relay; credentials are never accepted in this adapter or serialized into
    errors.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 587,
        sender: str,
        recipients: Sequence[str],
        timeout_seconds: float = 10.0,
        starttls: bool = True,
        client_factory: Callable[[str, int, float], smtplib.SMTP] | None = None,
    ) -> None:
        if not host or host != host.strip() or "\n" in host or "\r" in host:
            raise ValueError("SMTP host must be non-empty and single-line")
        if not 1 <= port <= 65535:
            raise ValueError("SMTP port must be between 1 and 65535")
        if not sender or "\n" in sender or "\r" in sender:
            raise ValueError("SMTP sender must be a valid single-line address")
        normalized = tuple(recipient.strip() for recipient in recipients)
        if not normalized or any(
            not value or "\n" in value or "\r" in value for value in normalized
        ):
            raise ValueError("SMTP recipients must be non-empty single-line addresses")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("SMTP timeout_seconds must be in (0, 300]")
        self._host = host
        self._port = port
        self._sender = sender
        self._recipients = normalized
        self._timeout = timeout_seconds
        self._starttls = starttls
        self._client_factory = client_factory or (
            lambda host, smtp_port, timeout: smtplib.SMTP(host, smtp_port, timeout=timeout)
        )

    def send(self, intent: NotificationIntent) -> str:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = ", ".join(self._recipients)
        message["Subject"] = intent.title
        message.set_content(intent.body)
        try:
            with self._client_factory(self._host, self._port, self._timeout) as client:
                if self._starttls:
                    client.starttls()
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise SmtpNotificationError("SMTP notification delivery failed") from exc
        return intent.id


__all__ = ("SmtpNotificationError", "SmtpNotificationSink")
