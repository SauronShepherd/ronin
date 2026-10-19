"""Bounded HTTPS notification adapter for alert and budget intents."""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
from collections.abc import Callable
from contextlib import closing
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    build_opener,
)

from .notifications import NotificationIntent


class WebhookNotificationError(RuntimeError):
    """Raised when a webhook notification cannot be delivered safely."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _open_without_redirects(request: Request, timeout: float) -> object:
    parsed = urlsplit(request.full_url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("webhook URL requires a hostname")
    port = parsed.port or 443
    try:
        addresses = tuple(
            sorted(
                {
                    ipaddress.ip_address(info[4][0]).compressed
                    for info in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
                }
            )
        )
    except (OSError, ValueError) as exc:
        raise OSError("webhook hostname could not be resolved safely") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise OSError("webhook hostname resolves to a non-public network")
    tls_context = ssl.create_default_context()

    class _PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self) -> None:
            last_error: OSError | None = None
            for address in addresses:
                try:
                    sock = socket.create_connection(
                        (address, self.port),
                        timeout=self.timeout,
                    )
                    try:
                        self.sock = tls_context.wrap_socket(sock, server_hostname=self.host)
                    except OSError:
                        sock.close()
                        raise
                    return
                except OSError as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
            raise OSError("webhook hostname has no connectable addresses")

    class _PinnedHTTPSHandler(HTTPSHandler):
        def https_open(self, req: Request) -> Any:
            return self.do_open(_PinnedHTTPSConnection, req)

    # The checked DNS answers are also the only addresses the transport can
    # connect to, closing the resolve-then-re-resolve SSRF race. Hostname-based
    # TLS verification remains enabled by HTTPSConnection.
    opener: OpenerDirector = build_opener(
        ProxyHandler({}), _RejectRedirects(), _PinnedHTTPSHandler()
    )
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
        try:
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError("port is outside the valid range")
        except ValueError as exc:
            raise ValueError("webhook URL must use a valid port") from exc
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
        request = Request(  # noqa: S310 - URL scheme is restricted to HTTPS at construction
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
