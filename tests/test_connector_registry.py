import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
import studio_connectors.http_json as http_json
from studio_connectors import (
    ConnectorCapabilityError,
    ConnectorCommitResult,
    ConnectorReadResult,
    ConnectorRegistry,
    HttpJsonConnector,
    PostgresConnector,
    S3JsonConnector,
    builtin_connector_registry,
)
from studio_connectors.contracts import Connector
from studio_connectors.http_json import (
    _retry_after_delay,
    _validate_endpoint_host,
    _validate_request_url,
)
from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectionId,
    ConnectorCapabilities,
    ConnectorDescriptor,
    SecretRef,
)
from studio_storage import EnvironmentSecretResolver


def test_builtin_connector_registry_is_explicit() -> None:
    registry = ConnectorRegistry((HttpJsonConnector(), PostgresConnector(), S3JsonConnector()))
    assert registry.ids() == ("http.json", "postgresql", "s3.json")
    assert registry.require("http.json").descriptor.capabilities.read
    assert registry.require("postgresql").descriptor.capabilities.discover
    with pytest.raises(KeyError):
        registry.require("unknown")


def test_connector_write_fails_closed_for_read_only_and_incomplete_adapters() -> None:
    connection = ConnectionDefinition(ConnectionId("sink"), "Sink", "test.sink")
    asset = AssetHandle(connection.id, (), "output")
    result = ConnectorReadResult((), ())
    secrets = EnvironmentSecretResolver({})
    registry = builtin_connector_registry()
    read_only_connection = ConnectionDefinition(ConnectionId("source"), "HTTP", "http.json")
    read_only_asset = AssetHandle(read_only_connection.id, (), "output")

    with pytest.raises(ConnectorCapabilityError, match="does not advertise writes"):
        registry.write(
            "http.json",
            read_only_connection,
            read_only_asset,
            result,
            secrets,
            idempotency_key="operation-1",
        )
    with pytest.raises(ConnectorCapabilityError, match="does not advertise transactional"):
        registry.write(
            "http.json",
            read_only_connection,
            read_only_asset,
            result,
            secrets,
            idempotency_key="operation-1",
            transactional=True,
        )
    with pytest.raises(ConnectorCapabilityError, match="different connector"):
        registry.write(
            "http.json",
            connection,
            asset,
            result,
            secrets,
            idempotency_key="operation-1",
        )
    with pytest.raises(ValueError, match="idempotency_key"):
        registry.write(
            "http.json",
            read_only_connection,
            read_only_asset,
            result,
            secrets,
            idempotency_key="operation\n1",
        )

    class IncompleteSink:
        descriptor = ConnectorDescriptor("test.sink", 1, ConnectorCapabilities(write=True))

        def discover(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
            return ()

        def read(self, *_args: object, **_kwargs: object) -> object:
            return result

    mismatched_asset = AssetHandle(ConnectionId("another-sink"), (), "output")
    incomplete_registry = ConnectorRegistry((cast(Connector, IncompleteSink()),))
    with pytest.raises(ConnectorCapabilityError, match="different connection"):
        incomplete_registry.write(
            "test.sink",
            connection,
            mismatched_asset,
            result,
            secrets,
            idempotency_key="operation-1",
        )

    with pytest.raises(ConnectorCapabilityError, match="does not implement it"):
        ConnectorRegistry((cast(Connector, IncompleteSink()),)).write(
            "test.sink",
            connection,
            asset,
            result,
            secrets,
            idempotency_key="operation-1",
        )


def test_connector_write_dispatches_and_validates_commit_receipts() -> None:
    connection = ConnectionDefinition(ConnectionId("sink"), "Sink", "test.sink")
    asset = AssetHandle(connection.id, (), "output")
    result = ConnectorReadResult((), ())
    secrets = EnvironmentSecretResolver({})

    class Sink:
        descriptor = ConnectorDescriptor(
            "test.sink", 1, ConnectorCapabilities(write=True, transactional_write=True)
        )
        calls: list[tuple[str, str]] = []

        def discover(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
            return ()

        def read(self, *_args: object, **_kwargs: object) -> object:
            return result

        def write(
            self,
            *_args: object,
            idempotency_key: str,
        ) -> ConnectorCommitResult:
            self.calls.append(("write", idempotency_key))
            return ConnectorCommitResult(
                idempotency_key,
                "commit-1",
                "output-1",
                "a" * 64,
                transactional=False,
                idempotency_enforced=True,
                delivery_semantics="exactly_once",
            )

        def transactional_write(
            self,
            *_args: object,
            idempotency_key: str,
        ) -> ConnectorCommitResult:
            self.calls.append(("transactional_write", idempotency_key))
            return ConnectorCommitResult(
                idempotency_key,
                "commit-2",
                "output-2",
                "b" * 64,
                transactional=True,
                idempotency_enforced=True,
                delivery_semantics="exactly_once",
            )

    sink = Sink()
    registry = ConnectorRegistry((cast(Connector, sink),))
    first = registry.write(
        "test.sink",
        connection,
        asset,
        result,
        secrets,
        idempotency_key="operation-1",
    )
    second = registry.write(
        "test.sink",
        connection,
        asset,
        result,
        secrets,
        idempotency_key="operation-2",
        transactional=True,
    )

    assert first.delivery_semantics == "exactly_once"
    assert first.transactional is False
    assert second.transactional is True
    assert sink.calls == [("write", "operation-1"), ("transactional_write", "operation-2")]


def test_connector_write_rejects_unproven_exactly_once_and_wrong_receipt() -> None:
    with pytest.raises(ValueError, match="provider-enforced idempotency"):
        ConnectorCommitResult(
            "operation-1",
            "commit-1",
            "output-1",
            "a" * 64,
            transactional=False,
            idempotency_enforced=False,
            delivery_semantics="exactly_once",
        )
    with pytest.raises(ValueError, match="control characters"):
        ConnectorCommitResult(
            "operation\n1",
            "commit-1",
            "output-1",
            "a" * 64,
            transactional=False,
            idempotency_enforced=False,
            delivery_semantics="at_least_once",
        )

    connection = ConnectionDefinition(ConnectionId("sink"), "Sink", "test.sink")
    asset = AssetHandle(connection.id, (), "output")
    read_result = ConnectorReadResult((), ())

    class WrongReceiptSink:
        descriptor = ConnectorDescriptor("test.sink", 1, ConnectorCapabilities(write=True))

        def discover(self, *_args: object, **_kwargs: object) -> tuple[object, ...]:
            return ()

        def read(self, *_args: object, **_kwargs: object) -> object:
            return read_result

        def write(
            self,
            *_args: object,
            idempotency_key: str,
        ) -> ConnectorCommitResult:
            del idempotency_key
            return ConnectorCommitResult(
                "different-key",
                "commit-1",
                "output-1",
                "a" * 64,
                transactional=False,
                idempotency_enforced=False,
                delivery_semantics="at_least_once",
            )

    with pytest.raises(ConnectorCapabilityError, match="changed the idempotency key"):
        ConnectorRegistry((cast(Connector, WrongReceiptSink()),)).write(
            "test.sink",
            connection,
            asset,
            read_result,
            EnvironmentSecretResolver({}),
            idempotency_key="operation-1",
        )


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


@pytest.mark.parametrize(
    "timeout_seconds",
    ["not-a-number", "0", "-1", "301", "nan", "inf", "-inf", "1e309"],
)
def test_http_connector_rejects_invalid_timeout_before_dns_secrets_or_transport(
    timeout_seconds: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def forbidden(label: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            calls.append(label)
            raise AssertionError(f"{label} must not be reached for invalid timeout")

        return fail

    monkeypatch.setattr(http_json.socket, "getaddrinfo", forbidden("dns"))
    monkeypatch.setattr(http_json, "_httpx", forbidden("transport"))
    resolver = EnvironmentSecretResolver({"RONIN_SECRET_HTTP_TOKEN": "secret"})
    monkeypatch.setattr(resolver, "resolve", forbidden("secrets"))
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(
            ("base_url", "https://provider.example/api"),
            ("timeout_seconds", timeout_seconds),
        ),
        secret_refs=(("bearer_token", SecretRef("secret://http/token")),),
    )

    with pytest.raises(ValueError, match="timeout_seconds"):
        HttpJsonConnector().read(
            connection,
            AssetHandle(connection.id, (), "events"),
            resolver,
        )

    assert calls == []


def test_http_connector_accepts_maximum_finite_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client_timeouts: list[float] = []
    request_timeouts: list[float] = []

    class Response:
        status_code = 200
        headers = {"content-type": "application/json", "content-length": "2"}

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"[]"

    class Client:
        def __init__(self, *, follow_redirects: bool, timeout: float) -> None:
            assert follow_redirects is False
            client_timeouts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def stream(self, _method: str, _url: str, *, headers, timeout: float) -> Response:
            del headers
            request_timeouts.append(timeout)
            return Response()

    class Httpx:
        class TimeoutException(Exception):
            pass

        class NetworkError(Exception):
            pass

    Httpx.Client = Client

    monkeypatch.setattr(http_json, "_httpx", lambda: Httpx)
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(
            ("allow_http", "true"),
            ("allow_private_network", "true"),
            ("base_url", "http://127.0.0.1/api"),
            ("timeout_seconds", "300"),
        ),
    )

    result = HttpJsonConnector().read(
        connection,
        AssetHandle(connection.id, (), "events"),
        EnvironmentSecretResolver({}),
    )

    assert result.rows == ()
    assert client_timeouts == [300.0]
    assert len(request_timeouts) == 1
    assert 0 < request_timeouts[0] <= 300.0


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
                ("retry_backoff_seconds", "5"),
                ("max_elapsed_seconds", "3"),
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


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "not-a-delay"])
def test_http_retry_after_rejects_non_finite_negative_and_malformed_values(value: str) -> None:
    with pytest.raises(ValueError, match="Retry-After"):
        _retry_after_delay(value, 0.0)


def test_http_retry_after_accepts_bounded_seconds_and_past_http_dates() -> None:
    assert _retry_after_delay("120", 0.0) == 60.0
    assert _retry_after_delay("Sat, 01 Jan 2000 00:00:00 GMT", 1.0) == 0.0


def test_http_connector_fails_before_retrying_malformed_retry_after() -> None:
    calls: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            calls.append(self.path)
            self.send_response(503)
            self.send_header("Retry-After", "NaN")
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
                ("max_retries", "2"),
            ),
        )
        with pytest.raises(ValueError, match="Retry-After seconds must be finite"):
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
