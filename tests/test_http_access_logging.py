from __future__ import annotations

import json
import logging
from http.client import HTTPResponse
from pathlib import Path
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from studio_core import Grant, GrantSet, ResourceScope
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_server.http import _Handler
from studio_storage import SqliteJobStore


def _request(url: str, *, token: str | None) -> HTTPResponse | HTTPError:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    request = Request(url, headers=headers)  # noqa: S310 - URL is the test's loopback server
    try:
        return cast(
            HTTPResponse | HTTPError,
            urlopen(request, timeout=5),  # noqa: S310 - loopback test server
        )
    except HTTPError as response:
        return response


def test_http_access_logs_are_structured_redacted_and_correlated(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    token = "".join(("test-secret", "-credential"))
    store = SqliteJobStore(
        tmp_path / "access-log-test.sqlite3",
        migration_now=Instant("2026-09-07T06:00:00.000000Z"),
    )
    service = DurableExecutionService(store, max_workers=1, max_in_flight=2)
    server = RoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        token=token,
        grants=GrantSet((Grant(frozenset({"read", "list"}), ResourceScope("*", None)),)),
    )
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    caplog.set_level(logging.INFO, logger="studio_server.http.access")

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        unauthorized = _request(f"{base_url}/v1/jobs", token=None)
        success = _request(f"{base_url}/v1/jobs?project=private-project", token=token)
        invalid = _request(
            f"{base_url}/v1/jobs?limit=0&project=private-project&secret=do-not-log",
            token=token,
        )

        assert unauthorized.status == 401
        assert success.status == 200
        assert invalid.status == 400
        request_ids = {
            unauthorized.headers["X-Ronin-Request-Id"],
            success.headers["X-Ronin-Request-Id"],
            invalid.headers["X-Ronin-Request-Id"],
        }
        assert len(request_ids) == 3

        records = [
            record for record in caplog.records if record.name == "studio_server.http.access"
        ]
        events = [json.loads(record.getMessage()) for record in records]
        assert {event["outcome"] for event in events} == {"OK", "WARN"}
        assert {event["status_code"] for event in events} == {200, 400, 401}
        assert {event["request_id"] for event in events} == request_ids
        assert all(event["route"] == "/v1/jobs" for event in events)
        assert all(event["event"] == "http.request" for event in events)
        assert all(isinstance(event["response_bytes"], int) for event in events)
        assert token not in caplog.text
        assert "private-project" not in caplog.text
        assert "do-not-log" not in caplog.text
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


def test_http_server_failures_are_logged_as_errors(caplog: pytest.LogCaptureFixture) -> None:
    handler = object.__new__(_Handler)
    handler._request_id = "req-test-server-error"
    handler.path = "/v1/jobs"
    handler.command = "GET"
    caplog.set_level(logging.INFO, logger="studio_server.http.access")

    handler.log_request(503)

    event = json.loads(caplog.records[-1].getMessage())
    assert caplog.records[-1].levelno == logging.ERROR
    assert event["outcome"] == "ERROR"
    assert event["status_code"] == 503


def test_scoped_runs_authenticate_before_requiring_a_project_filter(tmp_path: Path) -> None:
    token = "".join(("scoped-test", "-credential"))
    store = SqliteJobStore(
        tmp_path / "scoped-access-test.sqlite3",
        migration_now=Instant("2026-09-07T06:00:00.000000Z"),
    )
    service = DurableExecutionService(store, max_workers=1, max_in_flight=2)
    server = RoninHTTPServer(
        ("127.0.0.1", 0),
        service,
        token=token,
        grants=GrantSet(
            (
                Grant(
                    frozenset({"read", "list"}),
                    ResourceScope("project", "examples/demo"),
                ),
            )
        ),
    )
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        unauthenticated = _request(f"{base_url}/v1/jobs", token=None)
        invalid_token = _request(f"{base_url}/v1/jobs", token="".join(("bad", "-token")))
        missing_filter = _request(f"{base_url}/v1/jobs", token=token)
        allowed_filter = _request(f"{base_url}/v1/jobs?project=examples%2Fdemo", token=token)

        assert unauthenticated.status == 401
        assert invalid_token.status == 401
        assert missing_filter.status == 403
        assert allowed_filter.status == 200
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
