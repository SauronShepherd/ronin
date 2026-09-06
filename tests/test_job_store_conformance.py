from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

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
    StoredExecutionEvent,
)
from studio_storage import IdempotencyConflict, InMemoryJobStore, SqliteJobStore

NOW = "2026-09-06T09:00:00.000000Z"
BEFORE_EXPIRY = "2026-09-06T09:00:29.999999Z"
HEARTBEAT = "2026-09-06T09:00:10.000000Z"
EXPIRY = "2026-09-06T09:00:30.000000Z"
AFTER_EXPIRY = "2026-09-06T09:00:31.000000Z"


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


def _run(
    job_id: str = "job-1",
    run_id: str = "run-1",
    *,
    not_before: str = NOW,
) -> Run:
    return Run(
        id=RunId(run_id),
        job_id=JobId(job_id),
        ordinal=1,
        state=RunState.PENDING,
        not_before=not_before,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "memory":
        return InMemoryJobStore()
    return SqliteJobStore(tmp_path / "ronin.db", migration_now=NOW)


def _claim(store):
    claim = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now=NOW,
    )
    assert claim is not None
    return claim


def _write_kwargs(claim, *, now: str = HEARTBEAT) -> dict[str, object]:
    return {"owner": "worker-1", "lease_token": claim.lease_token, "now": now}


def _result() -> StoredCellResult:
    return StoredCellResult(
        RunId("run-1"),
        "cell-1",
        "a" * 64,
        "b" * 64,
        "succeeded",
        "{}",
        HEARTBEAT,
    )


def _evidence() -> StoredEvidenceRef:
    return StoredEvidenceRef(
        RunId("run-1"),
        "cell-1",
        "stdout",
        "sha256",
        "c" * 64,
        "text/plain",
        0,
        "artifact://sha256/" + "c" * 64,
    )


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
    assert (
        store.claim_next_run(
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            attempt_id=AttemptId("attempt-1"),
            lease_seconds=30,
            now=HEARTBEAT,
        )
        is None
    )


def test_claim_heartbeat_reclaim_and_replacement_attempt_same_run(store) -> None:
    store.create_job(_job(), _run())
    first = _claim(store)
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


def test_lease_expiry_boundary_is_identical_across_stores(store) -> None:
    store.create_job(_job(), _run())
    claim = _claim(store)
    assert store.reclaim_expired(now=BEFORE_EXPIRY) == ()
    assert not store.heartbeat(
        claim.attempt_id,
        owner="worker-1",
        lease_token=claim.lease_token,
        expires_at="2026-09-06T09:01:00.000000Z",
        now=EXPIRY,
    )
    assert store.reclaim_expired(now=EXPIRY) == (RunId("run-1"),)


def test_claim_respects_canonical_lexical_time_order(store) -> None:
    store.create_job(_job(), _run(not_before="2026-09-06T09:00:00.000001Z"))
    assert (
        store.claim_next_run(
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            attempt_id=AttemptId("attempt-1"),
            lease_seconds=30,
            now=NOW,
        )
        is None
    )
    claim = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now="2026-09-06T09:00:00.000001Z",
    )
    assert claim is not None


@pytest.mark.parametrize(
    "bad_now",
    [
        "2026-09-06T09:00:00Z",
        "2026-09-06T09:00:00.000Z",
        "2026-09-06T11:00:00.000000+02:00",
        "2026-09-06T09:00:00.000000+00:00",
        "2026-09-06T09:00:00.000000",
    ],
)
def test_store_boundaries_reject_noncanonical_instants(store, bad_now: str) -> None:
    store.create_job(_job(), _run())
    with pytest.raises(ValueError, match="canonical"):
        store.claim_next_run(
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            attempt_id=AttemptId("attempt-1"),
            lease_seconds=30,
            now=bad_now,
        )
    with pytest.raises(ValueError, match="canonical"):
        store.reclaim_expired(now=bad_now)


def test_attempt_event_sequences_are_per_attempt_and_run_read_is_ordered(store) -> None:
    store.create_job(_job(), _run())
    first = _claim(store)
    store.append_events(
        first.attempt_id,
        (
            StoredExecutionEvent(first.attempt_id, 0, "attempt.started", "", NOW),
            StoredExecutionEvent(first.attempt_id, 1, "cell.succeeded", "one", HEARTBEAT),
        ),
        **_write_kwargs(first),
    )
    with pytest.raises(ValueError, match="contiguous"):
        store.append_events(
            first.attempt_id,
            (StoredExecutionEvent(first.attempt_id, 3, "gap", "", HEARTBEAT),),
            **_write_kwargs(first),
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
        owner="worker-2",
        lease_token=second.lease_token,
        now=AFTER_EXPIRY,
    )
    events = store.read_events(RunId("run-1"), since=0)
    assert [(event.attempt_id, event.sequence) for event in events] == [
        (AttemptId("attempt-1"), 0),
        (AttemptId("attempt-1"), 1),
        (AttemptId("attempt-2"), 0),
    ]
    assert all(isinstance(event.occurred_at, Instant) for event in events)
    assert store.read_events(RunId("run-1"), since=2) == (events[2],)


def test_concurrent_duplicate_event_sequence_has_exactly_one_winner(store) -> None:
    store.create_job(_job(), _run())
    claim = _claim(store)
    writers = 8
    ready = Barrier(writers)

    def append(index: int) -> str:
        ready.wait()
        try:
            store.append_events(
                claim.attempt_id,
                (
                    StoredExecutionEvent(
                        claim.attempt_id,
                        0,
                        "attempt.raced",
                        f"writer-{index}",
                        HEARTBEAT,
                    ),
                ),
                **_write_kwargs(claim),
            )
        except ValueError as exc:
            return f"rejected:{exc}"
        return "accepted"

    with ThreadPoolExecutor(max_workers=writers) as executor:
        outcomes = list(executor.map(append, range(writers)))

    assert outcomes.count("accepted") == 1
    rejected = [outcome for outcome in outcomes if outcome != "accepted"]
    assert len(rejected) == writers - 1
    assert all(
        outcome == "rejected:event sequence must be contiguous within attempt"
        for outcome in rejected
    )


def test_cell_results_evidence_and_terminal_completion(store) -> None:
    store.create_job(_job(), _run())
    claim = _claim(store)
    result = _result()
    evidence = _evidence()
    store.put_cell_result(claim.attempt_id, result, **_write_kwargs(claim))
    store.put_evidence(claim.attempt_id, evidence, **_write_kwargs(claim))
    assert store.read_cell_results(RunId("run-1")) == (result,)
    assert isinstance(store.read_cell_results(RunId("run-1"))[0].updated_at, Instant)
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


def test_worker_writes_fail_closed_for_wrong_or_expired_lease(store) -> None:
    store.create_job(_job(), _run())
    claim = _claim(store)
    event = StoredExecutionEvent(claim.attempt_id, 0, "cell.succeeded", "", HEARTBEAT)

    for operation in (
        lambda: store.append_events(
            claim.attempt_id,
            (event,),
            owner="wrong",
            lease_token=claim.lease_token,
            now=HEARTBEAT,
        ),
        lambda: store.put_cell_result(
            claim.attempt_id,
            _result(),
            owner="wrong",
            lease_token=claim.lease_token,
            now=HEARTBEAT,
        ),
        lambda: store.put_evidence(
            claim.attempt_id,
            _evidence(),
            owner="wrong",
            lease_token=claim.lease_token,
            now=HEARTBEAT,
        ),
    ):
        with pytest.raises(ValueError, match="lease ownership lost"):
            operation()

    assert store.reclaim_expired(now=EXPIRY) == (RunId("run-1"),)
    with pytest.raises(ValueError, match="lease ownership lost"):
        store.put_cell_result(
            claim.attempt_id,
            _result(),
            **_write_kwargs(claim, now=EXPIRY),
        )
    assert store.read_cell_results(RunId("run-1")) == ()
    assert store.read_evidence(RunId("run-1")) == ()
    assert store.read_events(RunId("run-1"), since=0) == ()


def test_replacement_attempt_fences_stale_worker_and_can_write(store) -> None:
    store.create_job(_job(), _run())
    first = _claim(store)
    assert store.reclaim_expired(now=EXPIRY) == (RunId("run-1"),)
    second = store.claim_next_run(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=AttemptId("attempt-2"),
        lease_seconds=30,
        now=EXPIRY,
    )
    assert second is not None

    with pytest.raises(ValueError, match="lease ownership lost"):
        store.put_cell_result(
            first.attempt_id,
            _result(),
            owner="worker-1",
            lease_token=first.lease_token,
            now=EXPIRY,
        )

    result = _result()
    store.put_cell_result(
        second.attempt_id,
        result,
        owner="worker-2",
        lease_token=second.lease_token,
        now=EXPIRY,
    )
    assert store.read_cell_results(RunId("run-1")) == (result,)


def test_terminal_completion_rejects_expired_lease(store) -> None:
    store.create_job(_job(), _run())
    claim = _claim(store)
    with pytest.raises(ValueError, match="lease ownership lost"):
        store.complete_attempt(
            claim.attempt_id,
            state=AttemptState.SUCCEEDED,
            failure_code=None,
            owner="worker-1",
            lease_token=claim.lease_token,
            now=EXPIRY,
        )
