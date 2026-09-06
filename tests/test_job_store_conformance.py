from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from studio_orchestrator import (
    AttemptId,
    AttemptState,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    RunState,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)
from studio_storage import IdempotencyConflict, InMemoryJobStore, SqliteJobStore

NOW = "2026-09-06T09:00:00Z"
HEARTBEAT = "2026-09-06T09:00:10Z"
EXPIRY = "2026-09-06T09:00:30Z"
AFTER_EXPIRY = "2026-09-06T09:00:31Z"

StoreFactory = Callable[[], object]


def _job(job_id: str = "job-1", *, digest: str = "a" * 64) -> Job:
    return Job(
        id=JobId(job_id),
        project_id="project-1",
        idempotency_key="key-1",
        request_digest=digest,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )


def _run(job_id: str = "job-1", run_id: str = "run-1") -> Run:
    return Run(
        id=RunId(run_id),
        job_id=JobId(job_id),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "memory":
        return InMemoryJobStore()
    return SqliteJobStore(tmp_path / "ronin.db", migration_now=NOW)


def test_idempotency_replay_is_read_only_and_conflict_fails(store) -> None:
    original = store.create_job(_job(), _run())
    replay = store.create_job(_job("job-other"), _run("job-other", "run-other"))
    assert replay.id == original.id
    assert store.list_jobs(project_id=None, state=None, limit=100, cursor=None).items == (original,)

    with pytest.raises(IdempotencyConflict, match="different request"):
        store.create_job(_job("job-conflict", digest="b" * 64), _run("job-conflict", "run-x"))


def test_cancel_pending_terminalizes_without_attempt(store) -> None:
    store.create_job(_job(), _run())
    cancelled = store.request_cancel(JobId("job-1"), now=HEARTBEAT)
    assert cancelled.state is JobState.CANCELLED
    assert store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now=HEARTBEAT,
    ) is None


def test_claim_heartbeat_reclaim_and_replacement_attempt_same_run(store) -> None:
    store.create_job(_job(), _run())
    first = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now=NOW,
    )
    assert first is not None
    assert first.run.id == RunId("run-1")
    assert first.attempt_ordinal == 1
    assert first.run.state is RunState.RUNNING
    assert first.job.state is JobState.RUNNING

    assert not store.heartbeat(
        AttemptId("attempt-1"),
        owner="wrong",
        lease_token=LeaseToken("lease-1"),
        expires_at=EXPIRY,
        now=HEARTBEAT,
    )
    assert store.heartbeat(
        AttemptId("attempt-1"),
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        expires_at=EXPIRY,
        now=HEARTBEAT,
    )

    assert store.reclaim_expired(now=AFTER_EXPIRY) == (RunId("run-1"),)
    second = store.claim_next_run(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=AttemptId("attempt-2"),
        lease_seconds=30,
        now=AFTER_EXPIRY,
    )
    assert second is not None
    assert second.run.id == first.run.id
    assert second.attempt_ordinal == 2


def test_attempt_event_sequences_are_per_attempt_and_run_read_is_ordered(store) -> None:
    store.create_job(_job(), _run())
    first = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now=NOW,
    )
    assert first is not None
    store.append_events(
        first.attempt_id,
        (
            StoredExecutionEvent(first.attempt_id, 0, "attempt.started", "", NOW),
            StoredExecutionEvent(first.attempt_id, 1, "cell.succeeded", "one", HEARTBEAT),
        ),
    )
    with pytest.raises(ValueError, match="contiguous"):
        store.append_events(
            first.attempt_id,
            (StoredExecutionEvent(first.attempt_id, 3, "gap", "", HEARTBEAT),),
        )
    assert store.reclaim_expired(now=AFTER_EXPIRY) == (RunId("run-1"),)
    second = store.claim_next_run(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=AttemptId("attempt-2"),
        lease_seconds=30,
        now=AFTER_EXPIRY,
    )
    assert second is not None
    store.append_events(
        second.attempt_id,
        (StoredExecutionEvent(second.attempt_id, 0, "attempt.started", "", AFTER_EXPIRY),),
    )
    events = store.read_events(RunId("run-1"), since=0)
    assert [(event.attempt_id, event.sequence) for event in events] == [
        (AttemptId("attempt-1"), 0),
        (AttemptId("attempt-1"), 1),
        (AttemptId("attempt-2"), 0),
    ]
    assert store.read_events(RunId("run-1"), since=2) == (events[2],)


def test_cell_results_evidence_and_terminal_completion(store) -> None:
    store.create_job(_job(), _run())
    claim = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now=NOW,
    )
    assert claim is not None
    result = StoredCellResult(
        RunId("run-1"),
        "cell-1",
        "a" * 64,
        "b" * 64,
        "succeeded",
        "{}",
        HEARTBEAT,
    )
    evidence = StoredEvidenceRef(
        RunId("run-1"),
        "cell-1",
        "stdout",
        "sha256",
        "c" * 64,
        "text/plain",
        0,
        "artifact://sha256/" + "c" * 64,
    )
    store.put_cell_result(result)
    store.put_evidence(evidence)
    assert store.read_cell_results(RunId("run-1")) == (result,)
    assert store.read_evidence(RunId("run-1")) == (evidence,)

    store.complete_attempt(
        claim.attempt_id,
        state=AttemptState.SUCCEEDED,
        failure_code=None,
        owner="worker-1",
        lease_token=claim.lease_token,
        now=HEARTBEAT,
    )
    completed = store.get_job(JobId("job-1"))
    assert completed is not None
    assert completed.state is JobState.SUCCEEDED

    replay = store.create_job(_job("ignored"), _run("ignored", "ignored-run"))
    assert replay.id == completed.id
    assert replay.state is JobState.SUCCEEDED
