from __future__ import annotations

from pathlib import Path

import pytest
from studio_orchestrator import (
    AttemptId,
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
from studio_storage import SqliteJobStore

NOW = "2026-09-06T09:00:00.000000Z"
LATER = "2026-09-06T09:00:10.000000Z"


def _store(tmp_path: Path) -> SqliteJobStore:
    return SqliteJobStore(tmp_path / "ronin.db", migration_now=NOW)


def _seed_claim(store: SqliteJobStore, *, suffix: str = "1"):
    job = Job(
        id=JobId(f"job-{suffix}"),
        project_id="project-1",
        idempotency_key=f"key-{suffix}",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )
    run = Run(
        id=RunId(f"run-{suffix}"),
        job_id=job.id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    store.create_job(job, run)
    claim = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken(f"lease-{suffix}"),
        attempt_id=AttemptId(f"attempt-{suffix}"),
        lease_seconds=30,
        now=NOW,
    )
    assert claim is not None
    return claim


def test_fenced_sqlite_delegates_read_control_paths(tmp_path: Path) -> None:
    store = _store(tmp_path)
    claim = _seed_claim(store)
    assert store.get_job(JobId("job-1")) is not None
    assert store.list_jobs(
        project_id="project-1", state=JobState.RUNNING, limit=10, cursor=None
    ).items
    assert store.heartbeat(
        claim.attempt_id,
        owner="worker-1",
        lease_token=claim.lease_token,
        expires_at="2026-09-06T09:00:40.000000Z",
        now=LATER,
    )
    assert store.reclaim_expired(now=LATER) == ()


def test_fenced_sqlite_rejects_cross_run_result_and_evidence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    claim = _seed_claim(store)
    bad_result = StoredCellResult(
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
            bad_result,
            owner="worker-1",
            lease_token=claim.lease_token,
            now=LATER,
        )

    bad_evidence = StoredEvidenceRef(
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
            bad_evidence,
            owner="worker-1",
            lease_token=claim.lease_token,
            now=LATER,
        )
    assert store.read_cell_results(RunId("run-1")) == ()
    assert store.read_evidence(RunId("run-1")) == ()


@pytest.mark.parametrize(
    ("terminal_state", "expected_run", "expected_job", "failure_code"),
    [
        (AttemptState.CANCELLED, RunState.CANCELLED, JobState.CANCELLED, None),
        (AttemptState.FAILED, RunState.FAILED, JobState.FAILED, "cell_failed"),
        (AttemptState.SUCCEEDED, RunState.SUCCEEDED, JobState.SUCCEEDED, None),
    ],
)
def test_fenced_sqlite_terminal_completion_variants(
    tmp_path: Path,
    terminal_state: AttemptState,
    expected_run: RunState,
    expected_job: JobState,
    failure_code: str | None,
) -> None:
    store = _store(tmp_path)
    claim = _seed_claim(store)
    store.complete_attempt(
        claim.attempt_id,
        state=terminal_state,
        failure_code=failure_code,
        owner="worker-1",
        lease_token=claim.lease_token,
        now=LATER,
    )
    job = store.get_job(JobId("job-1"))
    assert job is not None
    assert job.state is expected_job
    if expected_job is JobState.FAILED:
        assert job.failure_code == failure_code
    assert store.list_jobs(project_id=None, state=expected_job, limit=10, cursor=None).items == (
        job,
    )
    assert (
        store.claim_next_run(
            owner="worker-2",
            lease_token=LeaseToken("lease-next"),
            attempt_id=AttemptId("attempt-next"),
            lease_seconds=30,
            now=LATER,
        )
        is None
    )


def test_fenced_sqlite_abandoned_attempt_requeues_same_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    claim = _seed_claim(store)
    store.complete_attempt(
        claim.attempt_id,
        state=AttemptState.ABANDONED,
        failure_code="worker_lost",
        owner="worker-1",
        lease_token=claim.lease_token,
        now=LATER,
    )
    replacement = store.claim_next_run(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=AttemptId("attempt-2"),
        lease_seconds=30,
        now=LATER,
    )
    assert replacement is not None
    assert replacement.run.id == RunId("run-1")
    assert replacement.attempt_ordinal == 2


def test_fenced_sqlite_rejects_nonterminal_completion(tmp_path: Path) -> None:
    store = _store(tmp_path)
    claim = _seed_claim(store)
    with pytest.raises(ValueError, match="terminal"):
        store.complete_attempt(
            claim.attempt_id,
            state=AttemptState.RUNNING,
            failure_code=None,
            owner="worker-1",
            lease_token=claim.lease_token,
            now=LATER,
        )


def test_request_cancel_still_delegates_atomically(tmp_path: Path) -> None:
    store = _store(tmp_path)
    job = Job(
        id=JobId("job-pending"),
        project_id="project-1",
        idempotency_key="key-pending",
        request_digest="d" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )
    run = Run(
        id=RunId("run-pending"),
        job_id=job.id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    store.create_job(job, run)
    cancelled = store.request_cancel(job.id, now=LATER)
    assert cancelled.state is JobState.CANCELLED
