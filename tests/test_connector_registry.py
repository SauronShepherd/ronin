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
from studio_connectors.http_json import _validate_endpoint_host
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId
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
