from dataclasses import dataclass, field
from typing import Mapping

import pytest

from pyronin import JobHandle, JobState, ProtocolError, Ronin


@dataclass
class FakeTransport:
    responses: list[object]
    calls: list[tuple[str, str, Mapping[str, object] | None, Mapping[str, str] | None, Mapping[str, str] | None]] = field(default_factory=list)

    def request(self, method: str, path: str, *, payload: Mapping[str, object] | None = None, headers: Mapping[str, str] | None = None, query: Mapping[str, str] | None = None) -> object:
        self.calls.append((method, path, payload, headers, query))
        return self.responses.pop(0)


def test_submit_status_cancel_events_and_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport([
        {"id": "job/a", "state": "queued"},
        {"id": "job/a", "state": "running"},
        [{"sequence": 0, "kind": "job.started", "message": "running"}],
        {"id": "job/a", "state": "cancelling"},
        {"id": "job/a", "state": "running"},
        {"id": "job/a", "state": "succeeded"},
    ])
    client = Ronin(transport=transport)
    job = client.submit(project="demo", target="etl", idempotency_key="once")
    assert job.id == "job/a"
    assert job.status() is JobState.RUNNING
    assert job.events()[0].kind == "job.started"
    assert job.cancel().state is JobState.CANCELLING
    monkeypatch.setattr("pyronin.time.sleep", lambda _: None)
    assert job.wait(poll_interval=0.01).state is JobState.SUCCEEDED
    assert transport.calls[0][3] == {"Idempotency-Key": "once"}


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


@pytest.mark.parametrize("payload", [{}, {"id": "", "state": "queued"}, {"id": "job", "state": "unknown"}, {"id": "job", "state": "failed", "failure_code": 7}])
def test_invalid_job_payloads_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ProtocolError):
        Ronin(transport=FakeTransport([payload])).get_job("job")
