from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.error import URLError

import pytest
from pyronin import HTTPTransport, JobState, ProtocolError, Ronin, TransportError


@dataclass
class FakeTransport:
    responses: list[object]
    calls: list[
        tuple[
            str,
            str,
            Mapping[str, object] | None,
            Mapping[str, str] | None,
            Mapping[str, str] | None,
        ]
    ] = field(default_factory=list)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, str] | None = None,
    ) -> object:
        self.calls.append((method, path, payload, headers, query))
        return self.responses.pop(0)


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


class _FlakyOpener:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def open(self, _request: object, *, timeout: float) -> _Response:
        assert timeout > 0
        self.calls += 1
        if self.calls <= self.failures:
            raise URLError("synthetic outage")
        return _Response(b'{"ok":true}')


def _job_payload(state: str) -> dict[str, object]:
    return {"id": "job/a", "state": state, "failure_code": None}


def test_submit_status_cancel_events_and_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport(
        [
            _job_payload("queued"),
            _job_payload("running"),
            {
                "items": [
                    {
                        "sequence": 0,
                        "attempt_id": "attempt-1",
                        "attempt_sequence": 0,
                        "kind": "job.started",
                        "message": "running",
                        "occurred_at": "2026-09-07T11:00:00.000000Z",
                    }
                ],
                "next_since": "next-events",
            },
            _job_payload("cancelling"),
            _job_payload("running"),
            _job_payload("succeeded"),
        ]
    )
    client = Ronin(transport=transport)
    job = client.submit(project="demo", target="etl", idempotency_key="once")
    assert job.id == "job/a"
    assert job.status() is JobState.RUNNING
    events = job.events(limit=25)
    assert events.items[0].kind == "job.started"
    assert events.items[0].attempt_id == "attempt-1"
    assert events.next_since == "next-events"
    assert transport.calls[2][4] == {"limit": "25"}
    assert job.cancel().state is JobState.CANCELLING
    monkeypatch.setattr("pyronin.time.sleep", lambda _: None)
    assert job.wait(poll_interval=0.01).state is JobState.SUCCEEDED
    assert transport.calls[0][3] == {"Idempotency-Key": "once"}


def test_client_retries_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = HTTPTransport(
        "https://example.test",
        max_retries=2,
        backoff_seconds=0.25,
    )
    opener = _FlakyOpener(failures=2)
    object.__setattr__(transport, "_opener", opener)
    sleeps: list[float] = []
    monkeypatch.setattr("pyronin.time.sleep", sleeps.append)

    assert transport.request("GET", "/health") == {"ok": True}
    assert opener.calls == 3
    assert sleeps == [0.25, 0.5]


def test_platform_plugins_parses_surface_metadata() -> None:
    transport = FakeTransport(
        [
            {
                "items": [
                    {
                        "id": "com.example.data",
                        "version": "1.0.0",
                        "state": "ready",
                        "error": None,
                    }
                ],
                "surfaces": [
                    {
                        "id": "com.example.data.preview",
                        "plugin_id": "com.example.data",
                        "namespace": "data",
                        "command": "preview",
                        "operation_id": "data.preview.v1",
                        "capability": "data:read",
                        "permission": "data:read",
                        "transport": "http",
                        "api_version": "1.0",
                        "path": "/v1/data/preview",
                        "method": "POST",
                    }
                ],
                "cli": [{
                    "id": "com.example.data.preview", "namespace": "data",
                    "command": "preview", "operation_id": "data.preview.v1", "options": ["limit"]
                }],
                "client_operations": [{
                    "id": "com.example.data.preview", "operation_id": "data.preview.v1",
                    "transport": "http", "path": "/v1/data/preview", "method": "POST"
                }],
            }
        ]
    )
    platform = Ronin(transport=transport).platform_plugins()
    assert platform.items[0].state == "ready"
    assert platform.surfaces[0].operation_id == "data.preview.v1"
    assert platform.cli[0].options == ("limit",)
    assert platform.client_operations[0].method == "POST"
    assert transport.calls[0][0:2] == ("GET", "/v1/platform/plugins")


def test_plugin_client_invokes_advertised_operation() -> None:
    transport = FakeTransport(
        [
            {
                "items": [],
                "surfaces": [{
                    "id": "com.example.data.preview", "plugin_id": "com.example.data",
                    "namespace": "data", "command": "preview", "operation_id": "data.preview.v1",
                    "capability": "data:read", "permission": "data:read", "transport": "http",
                    "api_version": "1.0", "path": "/v1/data/preview", "method": "POST",
                }],
            },
            {"ok": True},
        ]
    )
    result = Ronin(transport=transport).plugin("data").invoke(
        "data.preview.v1", payload={"limit": 10}
    )
    assert result == {"ok": True}
    assert transport.calls[1][0:3] == ("POST", "/v1/data/preview", {"limit": 10})


def test_plugin_client_expands_and_escapes_path_parameters() -> None:
    transport = FakeTransport(
        [
            {"items": [], "surfaces": [{
                "id": "com.example.run", "plugin_id": "com.example",
                "namespace": "example", "command": "run", "operation_id": "example.run.v1",
                "capability": "example.run", "permission": "example:execute", "transport": "http",
                "api_version": "1.0", "path": "/v1/example/labs/{lab_id}/runs", "method": "POST",
            }]},
            {"id": "run-1"},
        ]
    )
    result = Ronin(transport=transport).plugin("example").invoke(
        "example.run.v1", path_params={"lab_id": "lab/a"}, payload={"x": 1}
    )
    assert result == {"id": "run-1"}
    assert transport.calls[1][1] == "/v1/example/labs/lab%2Fa/runs"


def test_platform_plugins_rejects_malformed_surface_metadata() -> None:
    client = Ronin(transport=FakeTransport([{"items": [], "surfaces": [{"id": "bad"}]}]))
    with pytest.raises(ProtocolError, match="surface fields"):
        client.platform_plugins()


def test_unsafe_submission_without_idempotency_is_not_retried() -> None:
    transport = HTTPTransport("https://example.test", max_retries=3, backoff_seconds=0)
    opener = _FlakyOpener(failures=3)
    object.__setattr__(transport, "_opener", opener)

    with pytest.raises(TransportError):
        transport.request("POST", "/v1/jobs", payload={"project": "demo"})
    assert opener.calls == 1


def test_list_jobs_and_validation() -> None:
    transport = FakeTransport(
        [
            {
                "items": [{"id": "job-1", "state": "failed", "failure_code": "x"}],
                "next_cursor": "next-1",
            }
        ]
    )
    client = Ronin(transport=transport)
    page = client.list_jobs(project="demo", state=JobState.FAILED, limit=25, cursor="cursor-0")
    assert page.items[0].failure_code == "x"
    assert page.next_cursor == "next-1"
    assert transport.calls[0][4] == {
        "limit": "25",
        "project": "demo",
        "state": "failed",
        "cursor": "cursor-0",
    }
    with pytest.raises(ValueError):
        Ronin()
    with pytest.raises(ValueError):
        Ronin("https://example.test", transport=transport)
    with pytest.raises(ValueError):
        client.submit(project="", target="x")
    with pytest.raises(ValueError):
        client.list_jobs(project="")
    with pytest.raises(ValueError):
        client.list_jobs(limit=0)
    with pytest.raises(ValueError):
        client.list_jobs(cursor=" ")
    with pytest.raises(ValueError):
        client.get_events("job", limit=0)
    with pytest.raises(ValueError):
        client.get_events("job", since=" ")


def test_execute_sql_parses_result_and_sends_bounded_request() -> None:
    transport = FakeTransport(
        [
            {
                "columns": [{"name": "total", "type": "BIGINT"}],
                "rows": [[7]],
            }
        ]
    )
    client = Ronin(transport=transport)
    result = client.execute_sql(
        project="demo",
        sql="SELECT sum(value) AS total FROM events",
        parameters=("events",),
        max_rows=25,
    )
    assert result.columns[0].name == "total"
    assert result.rows == ((7,),)
    assert transport.calls[0][0:3] == (
        "POST",
        "/v1/sql",
        {
            "project": "demo",
            "sql": "SELECT sum(value) AS total FROM events",
            "parameters": ["events"],
            "max_rows": 25,
        },
    )
    with pytest.raises(ValueError):
        client.execute_sql(project="demo", sql="SELECT 1", max_rows=0)


@pytest.mark.parametrize(
    "payload",
    [
        {"columns": [{"name": "value", "type": "INTEGER", "extra": True}], "rows": []},
        {"columns": [{"name": "value", "type": "INTEGER"}], "rows": [[1, 2]]},
        {"columns": "not-an-array", "rows": []},
    ],
)
def test_invalid_sql_results_fail_closed(payload: object) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).execute_sql(project="demo", sql="SELECT 1")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"id": "", "state": "queued"},
        {"id": "job", "state": "unknown"},
        {"id": "job", "state": "failed", "failure_code": 7},
    ],
)
def test_invalid_job_payloads_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).get_job("job")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": [], "next_cursor": None, "extra": True},
        {"items": {}, "next_cursor": None},
        {"items": [], "next_cursor": ""},
    ],
)
def test_invalid_job_page_payloads_fail_closed(payload: object) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).list_jobs()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": [], "next_since": "cursor", "extra": True},
        {"items": {}, "next_since": "cursor"},
        {"items": [], "next_since": ""},
        {
            "items": [
                {
                    "sequence": 0,
                    "attempt_id": "attempt-1",
                    "attempt_sequence": -1,
                    "kind": "started",
                    "message": "x",
                    "occurred_at": "2026-09-07T11:00:00.000000Z",
                }
            ],
            "next_since": "cursor",
        },
    ],
)
def test_invalid_event_page_payloads_fail_closed(payload: object) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).get_events("job")
