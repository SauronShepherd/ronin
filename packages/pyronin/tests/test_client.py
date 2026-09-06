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


def test_submit_status_cancel_events_and_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport(
        [
            {"id": "job/a", "state": "queued"},
            {"id": "job/a", "state": "running"},
            [{"sequence": 0, "kind": "job.started", "message": "running"}],
            {"id": "job/a", "state": "cancelling"},
            {"id": "job/a", "state": "running"},
            {"id": "job/a", "state": "succeeded"},
        ]
    )
    client = Ronin(transport=transport)
    job = client.submit(project="demo", target="etl", idempotency_key="once")
    assert job.id == "job/a"
    assert job.status() is JobState.RUNNING
    assert job.events()[0].kind == "job.started"
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


def test_unsafe_submission_without_idempotency_is_not_retried() -> None:
    transport = HTTPTransport("https://example.test", max_retries=3, backoff_seconds=0)
    opener = _FlakyOpener(failures=3)
    object.__setattr__(transport, "_opener", opener)

    with pytest.raises(TransportError):
        transport.request("POST", "/v1/jobs", payload={"project": "demo"})
    assert opener.calls == 1


def test_list_jobs_and_validation() -> None:
    transport = FakeTransport([[{"id": "job-1", "state": "failed", "failure_code": "x"}]])
    client = Ronin(transport=transport)
    assert client.list_jobs(project="demo", state=JobState.FAILED)[0].failure_code == "x"
    assert transport.calls[0][4] == {"project": "demo", "state": "failed"}
    with pytest.raises(ValueError):
        Ronin()
    with pytest.raises(ValueError):
        Ronin("https://example.test", transport=transport)
    with pytest.raises(ValueError):
        client.submit(project="", target="x")
    with pytest.raises(ValueError):
        client.list_jobs(project="")


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
