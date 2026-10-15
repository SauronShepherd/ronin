import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest
from studio_connectors import (
    ConnectorRegistry,
    HttpJsonConnector,
    PostgresConnector,
    S3JsonConnector,
    builtin_connector_registry,
)
from studio_connectors.http_json import _validate_endpoint_host, _validate_request_url
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SecretRef
from studio_storage import EnvironmentSecretResolver


def test_builtin_connector_registry_is_explicit() -> None:
    registry = ConnectorRegistry((HttpJsonConnector(), PostgresConnector(), S3JsonConnector()))
    assert registry.ids() == ("http.json", "postgresql", "s3.json")
    assert registry.require("http.json").descriptor.capabilities.read
    assert registry.require("postgresql").descriptor.capabilities.discover
    with pytest.raises(KeyError):
        registry.require("unknown")


def test_connector_registry_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ConnectorRegistry((HttpJsonConnector(), HttpJsonConnector()))


def test_capability_record_round_trips_and_rejects_ambiguous_payloads() -> None:
    record = builtin_connector_registry().capability_records()[0]
    assert record.from_payload(record.to_payload()) == record
    payload = record.to_payload()
    payload["capabilities"] = dict(payload["capabilities"])
    del payload["capabilities"]["read"]
    with pytest.raises(ValueError, match="fields mismatch"):
        record.from_payload(payload)


def test_builtin_connector_registry_exposes_reference_profiles() -> None:
    assert builtin_connector_registry().ids() == (
        "azure.blob.json",
        "http.json",
        "jdbc",
        "ozone.s3.json",
        "postgresql",
        "s3.json",
    )


def test_http_connector_requires_https_by_default() -> None:
    connector = HttpJsonConnector()
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(("base_url", "http://example.test/api"),),
    )
    with pytest.raises(ValueError, match="HTTPS"):
        connector.discover(connection, EnvironmentSecretResolver({}))


def test_http_connector_allows_explicit_local_http_profile() -> None:
    connector = HttpJsonConnector()
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(
            ("allow_http", "true"),
            ("base_url", "http://localhost:8080/api"),
        ),
    )
    assert connector.discover(connection, EnvironmentSecretResolver({})) == ()


def test_http_connector_rejects_private_endpoint_without_explicit_opt_in() -> None:
    with pytest.raises(ValueError, match="private or reserved"):
        _validate_endpoint_host("127.0.0.1", allow_private=False)
    _validate_endpoint_host("127.0.0.1", allow_private=True)


def test_http_connector_revalidates_pagination_urls() -> None:
    with pytest.raises(ValueError, match="private or reserved"):
        _validate_request_url("http://127.0.0.1:8080/next", allow_http=True, allow_private=False)
    with pytest.raises(ValueError, match="disallowed scheme"):
        _validate_request_url("http://example.test/next", allow_http=False, allow_private=True)


def test_http_connector_paginates_and_retries_transient_responses() -> None:
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            query = parse_qs(urlsplit(self.path).query)
            page = query.get("page", ["1"])[0]
            calls.append(page)
            if page == "1" and calls.count("1") == 1:
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = '[{"id": 1}]' if page == "1" else '[{"id": 2}]'
            body = payload.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = ConnectionDefinition(
            ConnectionId("http-source"),
            "HTTP source",
            "http.json",
            options=(
                ("allow_http", "true"),
                ("allow_private_network", "true"),
                ("base_url", f"http://127.0.0.1:{server.server_port}"),
                ("page_param", "page"),
                ("page_size", "1"),
                ("max_pages", "2"),
                ("max_retries", "1"),
                ("retry_backoff_seconds", "0"),
            ),
        )
        result = HttpJsonConnector().read(
            connection,
            AssetHandle(connection.id, (), "events"),
            EnvironmentSecretResolver({}),
            limit=2,
        )
        assert [row["id"] for row in result.rows] == [1, 2]
        assert calls == ["1", "1", "2"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_connector_rejects_bearer_credentials_over_http() -> None:
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(
            ("allow_http", "true"),
            ("allow_private_network", "true"),
            ("base_url", "http://localhost:8080/api"),
        ),
        secret_refs=(("bearer_token", SecretRef("secret://http/token")),),
    )
    with pytest.raises(ValueError, match="HTTPS base_url"):
        HttpJsonConnector().read(
            connection,
            AssetHandle(connection.id, (), "events"),
            EnvironmentSecretResolver({"RONIN_SECRET_HTTP_TOKEN": "secret"}),
        )


def test_http_connector_rejects_cross_origin_pagination() -> None:
    foreign_calls: list[str] = []

    class ForeignHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            foreign_calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"[]")

        def log_message(self, *_args: object) -> None:
            return None

    foreign = ThreadingHTTPServer(("127.0.0.1", 0), ForeignHandler)
    foreign_thread = Thread(target=foreign.serve_forever, daemon=True)
    foreign_thread.start()

    class OriginHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps(
                {
                    "records": [],
                    "next": f"http://127.0.0.1:{foreign.server_port}/steal",
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return None

    origin = ThreadingHTTPServer(("127.0.0.1", 0), OriginHandler)
    origin_thread = Thread(target=origin.serve_forever, daemon=True)
    origin_thread.start()
    try:
        connection = ConnectionDefinition(
            ConnectionId("http-source"),
            "HTTP source",
            "http.json",
            options=(
                ("allow_http", "true"),
                ("allow_private_network", "true"),
                ("base_url", f"http://127.0.0.1:{origin.server_port}"),
                ("records_key", "records"),
                ("next_url_field", "next"),
                ("max_pages", "2"),
            ),
        )
        with pytest.raises(ValueError, match="remain on the base_url origin"):
            HttpJsonConnector().read(
                connection,
                AssetHandle(connection.id, (), "events"),
                EnvironmentSecretResolver({}),
            )
        assert foreign_calls == []
    finally:
        origin.shutdown()
        origin.server_close()
        origin_thread.join(timeout=2)
        foreign.shutdown()
        foreign.server_close()
        foreign_thread.join(timeout=2)


def test_http_connector_enforces_operation_wide_byte_budget() -> None:
    calls: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            page = int(parse_qs(urlsplit(self.path).query).get("page", ["1"])[0])
            calls.append(page)
            body = json.dumps([{"id": page}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = ConnectionDefinition(
            ConnectionId("http-source"),
            "HTTP source",
            "http.json",
            options=(
                ("allow_http", "true"),
                ("allow_private_network", "true"),
                ("base_url", f"http://127.0.0.1:{server.server_port}"),
                ("page_param", "page"),
                ("page_size", "1"),
                ("max_pages", "3"),
                ("max_response_bytes", "100"),
                ("max_total_bytes", "15"),
            ),
        )
        with pytest.raises(ValueError, match="operation exceeds configured byte budget"):
            HttpJsonConnector().read(
                connection,
                AssetHandle(connection.id, (), "events"),
                EnvironmentSecretResolver({}),
            )
        assert calls == [1, 2]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_connector_enforces_deadline_before_retry_sleep() -> None:
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            calls.append(self.path)
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = ConnectionDefinition(
            ConnectionId("http-source"),
            "HTTP source",
            "http.json",
            options=(
                ("allow_http", "true"),
                ("allow_private_network", "true"),
                ("base_url", f"http://127.0.0.1:{server.server_port}"),
                ("max_retries", "3"),
                ("retry_backoff_seconds", "1"),
                ("max_elapsed_seconds", "0.5"),
            ),
        )
        with pytest.raises(ValueError, match="operation exceeded its time budget"):
            HttpJsonConnector().read(
                connection,
                AssetHandle(connection.id, (), "events"),
                EnvironmentSecretResolver({}),
            )
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
