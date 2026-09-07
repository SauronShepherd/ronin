from __future__ import annotations

import pytest
from studio_orchestrator import (
    AttemptId,
    AttemptLimitExceeded,
    AttemptState,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    RunState,
    StoredCellResult,
    StoredEvidenceRef,
)
from studio_storage import InMemoryJobStore

NOW = "2026-09-06T09:00:00.000000Z"
LATER = "2026-09-06T09:00:10.000000Z"
EXPIRY = "2026-09-06T09:00:30.000000Z"
AFTER_EXPIRY = "2026-09-06T09:00:40.000000Z"


def _job(index: int) -> Job:
    return Job(
        id=JobId(f"job-{index}"),
        project_id="project-1" if index < 3 else "project-2",
        idempotency_key=f"key-{index}",
        request_digest=f"{index:x}" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )


def _run(index: int) -> Run:
    return Run(
        id=RunId(f"run-{index}"),
        job_id=JobId(f"job-{index}"),
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _claim(store: InMemoryJobStore, *, ordinal: int = 1):
    claim = store.claim_next_run(
        owner=f"worker-{ordinal}",
        lease_token=LeaseToken(f"lease-{ordinal}"),
        attempt_id=AttemptId(f"attempt-{ordinal}"),
        lease_seconds=30,
        now=NOW if ordinal == 1 else EXPIRY,
    )
    assert claim is not None
    return claim


def test_list_jobs_validates_bounds_and_paginates_filters() -> None:
    store = InMemoryJobStore()
    for index in range(1, 5):
        store.create_job(_job(index), _run(index))

    with pytest.raises(ValueError, match="between 1 and 100"):
        store.list_jobs(project_id=None, state=None, limit=0, cursor=None)
    with pytest.raises(ValueError, match="between 1 and 100"):
        store.list_jobs(project_id=None, state=None, limit=101, cursor=None)

    first = store.list_jobs(project_id="project-1", state=JobState.QUEUED, limit=1, cursor=None)
    assert [job.id for job in first.items] == [JobId("job-2")]
    assert first.next_cursor is not None
    second = store.list_jobs(
        project_id="project-1", state=JobState.QUEUED, limit=2, cursor=first.next_cursor
    )
    assert [job.id for job in second.items] == [JobId("job-1")]
    assert second.next_cursor is None


def test_create_job_rejects_identity_and_run_ownership_mismatch() -> None:
    store = InMemoryJobStore()
    store.create_job(_job(1), _run(1))

    duplicate = Job(
        id=JobId("job-1"),
        project_id="project-1",
        idempotency_key="different-key",
        request_digest="f" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(ValueError, match="identity already exists"):
        store.create_job(duplicate, _run(2))

    with pytest.raises(ValueError, match="run must belong to job"):
        store.create_job(_job(3), _run(4))


def test_active_cancel_transitions_job_to_cancelling() -> None:
    store = InMemoryJobStore()
    store.create_job(_job(1), _run(1))
    _claim(store)

    cancelled = store.request_cancel(JobId("job-1"), now=LATER)
    assert cancelled.state is JobState.CANCELLING


def test_terminal_cancel_is_idempotent_and_empty_claim_returns_none() -> None:
    store = InMemoryJobStore()
    assert (
        store.claim_next_run(
            owner="worker-1",
            lease_token=LeaseToken("lease-empty"),
            attempt_id=AttemptId("attempt-empty"),
            lease_seconds=30,
            now=NOW,
        )
        is None
    )
    store.create_job(_job(1), _run(1))
    cancelled = store.request_cancel(JobId("job-1"), now=LATER)
    assert cancelled.state is JobState.CANCELLED
    assert store.request_cancel(JobId("job-1"), now=AFTER_EXPIRY) == cancelled


def test_heartbeat_validation_and_lease_identity_fail_closed() -> None:
    store = InMemoryJobStore()
    store.create_job(_job(1), _run(1))
    claim = _claim(store)

    with pytest.raises(ValueError, match="after now"):
        store.heartbeat(
            claim.attempt_id,
            owner="worker-1",
            lease_token=claim.lease_token,
            expires_at=LATER,
            now=LATER,
        )
    assert not store.heartbeat(
        AttemptId("missing"),
        owner="worker-1",
        lease_token=claim.lease_token,
        expires_at=EXPIRY,
        now=LATER,
    )
    assert not store.heartbeat(
        claim.attempt_id,
        owner="worker-other",
        lease_token=claim.lease_token,
        expires_at=AFTER_EXPIRY,
        now=LATER,
    )
    assert not store.heartbeat(
        claim.attempt_id,
        owner="worker-1",
        lease_token=claim.lease_token,
        expires_at=AFTER_EXPIRY,
        now=EXPIRY,
    )


def test_read_events_rejects_negative_offset() -> None:
    store = InMemoryJobStore()
    with pytest.raises(ValueError, match="non-negative"):
        store.read_events(RunId("run-1"), since=-1)


def test_direct_cancelled_completion_closes_running_job() -> None:
    store = InMemoryJobStore()
    store.create_job(_job(1), _run(1))
    claim = _claim(store)
    store.complete_attempt(
        claim.attempt_id,
        state=AttemptState.CANCELLED,
        failure_code=None,
        owner="worker-1",
        lease_token=claim.lease_token,
        now=LATER,
    )
    job = store.get_job(JobId("job-1"))
    assert job is not None
    assert job.state is JobState.CANCELLED


def test_memory_rejects_cross_run_result_and_evidence() -> None:
    store = InMemoryJobStore()
    store.create_job(_job(1), _run(1))
    claim = _claim(store)
    result = StoredCellResult(
        RunId("run-other"),
        "cell-1",
        "a" * 64,
        "b" * 64,
        "succeeded",
        "{}",
        Instant(LATER),
    )
    with pytest.raises(ValueError, match="run does not match attempt"):
        store.put_cell_result(
            claim.attempt_id,
            result,
            owner="worker-1",
            lease_token=claim.lease_token,
            now=LATER,
        )

    evidence = StoredEvidenceRef(
        RunId("run-other"),
        "cell-1",
        "stdout",
        "sha256",
        "c" * 64,
        "text/plain",
        1,
        "artifact://sha256/" + "c" * 64,
    )
    with pytest.raises(ValueError, match="run does not match attempt"):
        store.put_evidence(
            claim.attempt_id,
            evidence,
            owner="worker-1",
            lease_token=claim.lease_token,
            now=LATER,
        )


def test_claim_validates_lease_seconds_and_attempt_limit() -> None:
    store = InMemoryJobStore()
    store.create_job(_job(1), _run(1))
    with pytest.raises(ValueError, match="positive"):
        store.claim_next_run(
            owner="worker-1",
            lease_token=LeaseToken("lease-0"),
            attempt_id=AttemptId("attempt-0"),
            lease_seconds=0,
            now=NOW,
        )

    current = NOW
    for ordinal in range(1, 11):
        claim = store.claim_next_run(
            owner=f"worker-{ordinal}",
            lease_token=LeaseToken(f"lease-{ordinal}"),
            attempt_id=AttemptId(f"attempt-{ordinal}"),
            lease_seconds=1,
            now=current,
        )
        assert claim is not None
        current = f"2026-09-06T09:00:{ordinal:02d}.000000Z"
        assert store.reclaim_expired(now=current) == (RunId("run-1"),)

    with pytest.raises(AttemptLimitExceeded, match="attempt limit"):
        store.claim_next_run(
            owner="worker-11",
            lease_token=LeaseToken("lease-11"),
            attempt_id=AttemptId("attempt-11"),
            lease_seconds=1,
            now=current,
        )
    failed = store.get_job(JobId("job-1"))
    assert failed is not None
    assert failed.state is JobState.FAILED
    assert failed.failure_code == "attempt_limit_exceeded"
