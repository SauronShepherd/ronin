"""HTTP JSON connector qualification against a real loopback HTTP service."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from studio_connectors import ConnectorReadResult, HttpJsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId
from studio_storage import EnvironmentSecretResolver

Responder = Callable[[BaseHTTPRequestHandler], None]


@contextmanager
def _http_service(responder: Responder) -> Iterator[tuple[str, list[str]]]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            requests.append(self.path)
            responder(self)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _json_response(
    handler: BaseHTTPRequestHandler,
    payload: object,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)


def _read(
    origin: str,
    *,
    options: tuple[tuple[str, str], ...] = (),
) -> ConnectorReadResult:
    connection = ConnectionDefinition(
        ConnectionId("http-real"),
        "Loopback HTTP JSON qualification",
        "http.json",
        options=(
            ("allow_http", "true"),
            ("allow_private_network", "true"),
            ("base_url", f"{origin}/api"),
            ("timeout_seconds", "2"),
            *options,
        ),
    )
    asset = AssetHandle(connection.id, ("v1",), "records")
    return HttpJsonConnector().read(connection, asset, EnvironmentSecretResolver({}))


def test_http_json_reads_paginated_records_and_snapshot_replay() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        page = parse_qs(urlsplit(handler.path).query).get("page", ["1"])[0]
        records = (
            [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]
            if page == "1"
            else [{"id": 3, "name": "Linus"}]
        )
        _json_response(handler, records)

    with _http_service(responder) as (origin, requests):
        connection = ConnectionDefinition(
            ConnectionId("http-real"),
            "Loopback HTTP JSON qualification",
            "http.json",
            options=(
                ("allow_http", "true"),
                ("allow_private_network", "true"),
                ("base_url", f"{origin}/api"),
                ("page_param", "page"),
                ("page_size", "2"),
                ("max_pages", "3"),
                ("timeout_seconds", "2"),
            ),
        )
        asset = AssetHandle(connection.id, ("v1",), "records")
        connector = HttpJsonConnector()
        secrets = EnvironmentSecretResolver({})

        first = connector.read(connection, asset, secrets, limit=3)
        replay = connector.read(
            connection,
            asset,
            secrets,
            limit=3,
            checkpoint=first.checkpoint,
        )

    assert first.rows == (
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Grace"},
        {"id": 3, "name": "Linus"},
    )
    assert {field.name for field in first.fields} == {"id", "name"}
    assert first.checkpoint.strategy == "snapshot"
    assert first.checkpoint.value
    assert replay.rows == ()
    assert replay.checkpoint == first.checkpoint
    assert requests == [
        "/api/v1/records?page=1",
        "/api/v1/records?page=2",
        "/api/v1/records?page=1",
        "/api/v1/records?page=2",
    ]


def test_http_json_does_not_report_page_param_limit_as_complete_snapshot() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        _json_response(handler, [{"id": 1}])

    with (
        _http_service(responder) as (origin, requests),
        pytest.raises(ValueError, match="reached max_pages before completion"),
    ):
        _read(
            origin,
            options=(
                ("page_param", "page"),
                ("page_size", "1"),
                ("max_pages", "1"),
            ),
        )

    assert requests == ["/api/v1/records?page=1"]


def test_http_json_does_not_report_next_url_limit_as_complete_snapshot() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        _json_response(
            handler,
            {
                "records": [{"id": 1}],
                "next": f"{origin}/api/v1/records?page=2",
            },
        )

    with (
        _http_service(responder) as (origin, requests),
        pytest.raises(ValueError, match="reached max_pages before completion"),
    ):
        _read(
            origin,
            options=(
                ("records_key", "records"),
                ("next_url_field", "next"),
                ("max_pages", "1"),
            ),
        )

    assert requests == ["/api/v1/records"]


def test_http_json_stops_repeated_next_url_before_repeating_the_request() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        _json_response(
            handler,
            {"records": [{"id": 1}], "next": f"{origin}/api/v1/records"},
        )

    with (
        _http_service(responder) as (origin, requests),
        pytest.raises(ValueError, match="pagination URL repeated"),
    ):
        _read(
            origin,
            options=(
                ("records_key", "records"),
                ("next_url_field", "next"),
                ("max_pages", "100"),
            ),
        )

    assert requests == ["/api/v1/records"]


def test_http_json_retries_real_service_503_and_succeeds() -> None:
    attempts = 0

    def responder(handler: BaseHTTPRequestHandler) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            _json_response(handler, {"error": "temporarily unavailable"}, status=503)
            return
        _json_response(handler, [{"id": 7}])

    with _http_service(responder) as (origin, requests):
        result = _read(
            origin,
            options=(
                ("max_retries", "1"),
                ("retry_backoff_seconds", "0"),
            ),
        )

    assert attempts == 2
    assert requests == ["/api/v1/records", "/api/v1/records"]
    assert result.rows == ({"id": 7},)


def test_http_json_rejects_real_service_redirects() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(302)
        handler.send_header("Location", "http://127.0.0.1:1/redirected")
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    with (
        _http_service(responder) as (origin, _requests),
        pytest.raises(ValueError, match="HTTP redirects are disabled"),
    ):
        _read(origin)


def test_http_json_enforces_response_byte_limit_from_real_service() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        _json_response(handler, [{"id": 123456789}])

    with (
        _http_service(responder) as (origin, _requests),
        pytest.raises(ValueError, match="response exceeds configured byte limit"),
    ):
        _read(origin, options=(("max_response_bytes", "8"),))


def test_http_json_rejects_cross_origin_next_page_from_real_service() -> None:
    def responder(handler: BaseHTTPRequestHandler) -> None:
        _json_response(
            handler,
            {"records": [{"id": 1}], "next": "http://127.0.0.1:1/outside"},
        )

    with _http_service(responder) as (origin, requests):
        connection = ConnectionDefinition(
            ConnectionId("http-real"),
            "Loopback HTTP JSON qualification",
            "http.json",
            options=(
                ("allow_http", "true"),
                ("allow_private_network", "true"),
                ("base_url", f"{origin}/api"),
                ("records_key", "records"),
                ("next_url_field", "next"),
                ("max_pages", "2"),
            ),
        )
        asset = AssetHandle(connection.id, ("v1",), "records")
        with pytest.raises(ValueError, match="pagination URL must remain on the base_url origin"):
            HttpJsonConnector().read(connection, asset, EnvironmentSecretResolver({}))

    assert requests == ["/api/v1/records"]
