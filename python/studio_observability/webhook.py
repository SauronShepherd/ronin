"""Bounded HTTPS notification adapter for alert and budget intents."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import closing
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

from .notifications import NotificationIntent


class WebhookNotificationError(RuntimeError):
    """Raised when a webhook notification cannot be delivered safely."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _open_without_redirects(request: Request, timeout: float) -> object:
    opener: OpenerDirector = build_opener(_RejectRedirects())
    return opener.open(request, timeout=timeout)


class WebhookNotificationSink:
    """POST notification intents to one HTTPS endpoint with bounded I/O."""

    def __init__(
        self,
        url: str,
        *,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = 1_048_576,
        transport: Callable[[Request, float], object] | None = None,
    ) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("webhook URL must be an HTTPS URL without embedded credentials")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("webhook timeout_seconds must be in (0, 300]")
        if max_response_bytes < 1 or max_response_bytes > 10 * 1024 * 1024:
            raise ValueError("webhook max_response_bytes must be between 1 and 10485760")
        self._url = url
        self._timeout = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport or _open_without_redirects

    def send(self, intent: NotificationIntent) -> str:
        body = json.dumps(
            {
                "id": intent.id,
                "kind": intent.kind,
                "title": intent.title,
                "body": intent.body,
                "created_at": str(intent.created_at),
                "attributes": dict(intent.attributes),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self._url,
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = cast(Any, self._transport(request, self._timeout))
            status = int(getattr(response, "status", 200))
            with closing(response):
                raw = response.read(self._max_response_bytes + 1)
                if len(raw) > self._max_response_bytes:
                    raise WebhookNotificationError("webhook response exceeds configured byte limit")
        except (HTTPError, URLError, OSError) as exc:
            raise WebhookNotificationError("webhook notification delivery failed") from exc
        if status < 200 or status >= 300:
            raise WebhookNotificationError(f"webhook returned HTTP status {status}")
        return intent.id


__all__ = ("WebhookNotificationError", "WebhookNotificationSink")
