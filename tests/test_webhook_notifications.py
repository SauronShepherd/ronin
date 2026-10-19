from __future__ import annotations

import socket
from io import BytesIO
from urllib.request import Request

import pytest
import studio_observability.webhook as webhook
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
    with pytest.raises(ValueError, match="valid port"):
        WebhookNotificationSink("https://alerts.example.test:invalid/hook")
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


def test_default_webhook_transport_rejects_non_public_dns_before_connect(monkeypatch) -> None:
    def resolve(_host, _port, *, type):
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    def forbidden_connect(*_args, **_kwargs):
        pytest.fail("webhook transport connected before rejecting a private address")

    monkeypatch.setattr(webhook.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(webhook.socket, "create_connection", forbidden_connect)

    with pytest.raises(OSError, match="non-public network"):
        webhook._open_without_redirects(Request("https://hooks.example.test/notify"), 1.0)


def test_default_webhook_transport_rejects_mixed_public_and_private_dns(monkeypatch) -> None:
    def resolve(_host, _port, *, type):
        assert type == socket.SOCK_STREAM
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443)),
        ]

    monkeypatch.setattr(webhook.socket, "getaddrinfo", resolve)

    with pytest.raises(OSError, match="non-public network"):
        webhook._open_without_redirects(Request("https://hooks.example.test/notify"), 1.0)


def test_default_webhook_transport_connects_to_the_validated_dns_address(monkeypatch) -> None:
    resolutions: list[str] = []
    connections: list[tuple[str, int]] = []

    def resolve(host, port, *, type):
        assert type == socket.SOCK_STREAM
        resolutions.append(host)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ]

    def connect(address, *, timeout):
        del timeout
        connections.append(address)
        raise OSError("stop before TLS")

    monkeypatch.setattr(webhook.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(webhook.socket, "create_connection", connect)

    with pytest.raises(OSError, match="stop before TLS"):
        webhook._open_without_redirects(Request("https://hooks.example.test/notify"), 1.0)

    assert resolutions == ["hooks.example.test"]
    assert connections == [("93.184.216.34", 443)]


def test_default_webhook_transport_posts_over_tls_to_the_pinned_address(monkeypatch) -> None:
    connected: list[tuple[str, int]] = []
    sent: list[bytes] = []
    verified_hosts: list[str | None] = []

    class _Socket:
        def settimeout(self, _timeout) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            sent.append(data)

        def makefile(self, _mode: str):
            return BytesIO(b"HTTP/1.1 202 Accepted\r\nContent-Length: 2\r\n\r\nok")

        def close(self) -> None:
            pass

    class _TlsContext:
        def wrap_socket(self, sock, *, server_hostname: str | None):
            verified_hosts.append(server_hostname)
            return sock

    def resolve(_host, port, *, type):
        assert type == socket.SOCK_STREAM
        assert port == 443
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    def connect(address, *, timeout):
        del timeout
        connected.append(address)
        return _Socket()

    monkeypatch.setattr(webhook.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(webhook.socket, "create_connection", connect)
    monkeypatch.setattr(webhook.ssl, "create_default_context", _TlsContext)

    response = webhook._open_without_redirects(
        Request(
            "https://hooks.example.test/notify",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        2.0,
    )
    try:
        assert response.status == 202
        assert response.read() == b"ok"
    finally:
        response.close()

    assert connected == [("93.184.216.34", 443)]
    assert verified_hosts == ["hooks.example.test"]
    assert b"POST /notify HTTP/1.1" in sent[0]
    assert b"Host: hooks.example.test" in sent[0]
