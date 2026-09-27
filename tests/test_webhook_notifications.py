from __future__ import annotations

import pytest

from studio_observability import (
    NotificationIntent,
    WebhookNotificationError,
    WebhookNotificationSink,
)
from studio_orchestrator import Instant


class _Response:
    def __init__(self, status: int = 202, body: bytes = b"ok") -> None:
        self.status = status
        self.body = body
        self.request_body: bytes | None = None
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def read(self, limit: int) -> bytes:
        del limit
        return self.body


def _intent() -> NotificationIntent:
    return NotificationIntent(
        "notification-1",
        "alert",
        "Queue lag",
        "Queue lag is high.",
        Instant("2026-09-15T00:00:00.000000Z"),
        (("rule_id", "queue"),),
    )


def test_webhook_sink_posts_bounded_json_and_returns_intent_id() -> None:
    response = _Response()
    seen: dict[str, object] = {}

    def transport(request, timeout):
        seen["method"] = request.method
        seen["body"] = request.data
        seen["timeout"] = timeout
        return response

    sink = WebhookNotificationSink("https://alerts.example.test/hook", transport=transport)
    assert sink.send(_intent()) == "notification-1"
    assert seen["method"] == "POST"
    assert b'"id":"notification-1"' in seen["body"]
    assert seen["timeout"] == 10.0
    assert response.closed


def test_webhook_sink_rejects_insecure_urls_and_non_success() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        WebhookNotificationSink("http://alerts.example.test/hook")
    response = _Response(503)
    sink = WebhookNotificationSink(
        "https://alerts.example.test/hook", transport=lambda *_: response
    )
    with pytest.raises(WebhookNotificationError, match="HTTP status 503"):
        sink.send(_intent())


def test_webhook_sink_rejects_oversized_response() -> None:
    response = _Response(body=b"12345")
    sink = WebhookNotificationSink(
        "https://alerts.example.test/hook", max_response_bytes=4, transport=lambda *_: response
    )
    with pytest.raises(WebhookNotificationError, match="byte limit"):
        sink.send(_intent())
