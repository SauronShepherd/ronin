from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from studio_orchestrator import (
    AttemptId,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunExecutionEvent,
    RunId,
    RunState,
    StoredExecutionEvent,
)
from studio_storage import BoundedAsyncJobStore, InMemoryJobStore, SqliteJobStore, paged_store
from studio_storage.fenced_sqlite import SqliteJobStore as CanonicalSqliteJobStore

NOW = "2026-09-07T09:00:00.000000Z"
AFTER_EXPIRY = "2026-09-07T09:00:31.000000Z"
SECOND_ATTEMPT_WRITE = "2026-09-07T09:00:32.000000Z"


def test_exported_sqlite_store_owns_service_read_contracts() -> None:
    assert SqliteJobStore is CanonicalSqliteJobStore
    assert not hasattr(paged_store, "SqliteJobStore")
    assert "list_jobs" in SqliteJobStore.__dict__
    assert "read_event_page" in SqliteJobStore.__dict__


def _job(job_id: str, created_at: str, *, project_id: str = "project-1") -> Job:
    return Job(
        id=JobId(job_id),
        project_id=project_id,
        idempotency_key=f"key-{job_id}",
        request_digest=(job_id.encode("utf-8").hex() + "0" * 64)[:64],
        state=JobState.QUEUED,
        created_at=created_at,
        updated_at=created_at,
    )


def _run(job_id: str, created_at: str) -> Run:
    return Run(
        id=RunId(f"run-{job_id}"),
        job_id=JobId(job_id),
        ordinal=1,
        state=RunState.PENDING,
        not_before=created_at,
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "memory":
        return InMemoryJobStore()
    return SqliteJobStore(tmp_path / "ronin.db", migration_now=NOW)


def _create(store, job_id: str, created_at: str, *, project_id: str = "project-1") -> None:
    store.create_job(
        _job(job_id, created_at, project_id=project_id),
        _run(job_id, created_at),
    )


def test_list_jobs_is_newest_first_keyset_stable_under_concurrent_insert(store) -> None:
    _create(store, "job-a", "2026-09-07T09:00:01.000000Z")
    _create(store, "job-b", "2026-09-07T09:00:02.000000Z")
    _create(store, "job-c", "2026-09-07T09:00:03.000000Z")

    first = store.list_jobs(project_id=None, state=None, limit=2, cursor=None)
    assert [str(job.id) for job in first.items] == ["job-c", "job-b"]
    assert first.next_cursor is not None

    _create(store, "job-new", "2026-09-07T09:00:04.000000Z")

    second = store.list_jobs(
        project_id=None,
        state=None,
        limit=2,
        cursor=first.next_cursor,
    )
    assert [str(job.id) for job in second.items] == ["job-a"]
    assert second.next_cursor is None

    restarted = store.list_jobs(project_id=None, state=None, limit=2, cursor=None)
    assert [str(job.id) for job in restarted.items] == ["job-new", "job-c"]


def test_list_jobs_breaks_created_at_ties_by_job_id_descending(store) -> None:
    timestamp = "2026-09-07T09:00:01.000000Z"
    _create(store, "job-a", timestamp)
    _create(store, "job-b", timestamp)

    first = store.list_jobs(project_id=None, state=None, limit=1, cursor=None)
    assert [str(job.id) for job in first.items] == ["job-b"]
    assert first.next_cursor is not None
    second = store.list_jobs(
        project_id=None,
        state=None,
        limit=1,
        cursor=first.next_cursor,
    )
    assert [str(job.id) for job in second.items] == ["job-a"]


def test_job_cursor_is_fail_closed_and_bound_to_filters(store) -> None:
    _create(store, "job-a", "2026-09-07T09:00:01.000000Z")
    _create(store, "job-b", "2026-09-07T09:00:02.000000Z")
    first = store.list_jobs(project_id="project-1", state=JobState.QUEUED, limit=1, cursor=None)
    assert first.next_cursor is not None

    with pytest.raises(ValueError, match="cursor"):
        store.list_jobs(project_id=None, state=None, limit=1, cursor="not-a-valid-cursor")
    with pytest.raises(ValueError, match="filters"):
        store.list_jobs(
            project_id="project-other",
            state=JobState.QUEUED,
            limit=1,
            cursor=first.next_cursor,
        )
    with pytest.raises(ValueError, match="filters"):
        store.list_jobs(
            project_id="project-1",
            state=None,
            limit=1,
            cursor=first.next_cursor,
        )


def test_cursor_decoders_reject_oversize_non_object_and_schema_drift() -> None:
    with pytest.raises(ValueError, match="invalid cursor"):
        paged_store._decode_cursor("x" * 1025)
    with pytest.raises(ValueError, match="invalid cursor"):
        paged_store._decode_cursor(
            paged_store._encode_cursor({"payload": [1, 2]}).replace("eyJ", "WzE")
        )

    wrong_job_version = paged_store._encode_cursor(
        {
            "v": 2,
            "kind": "jobs",
            "created_at": NOW,
            "job_id": "job-1",
            "project_id": None,
            "state": None,
        }
    )
    wrong_job_kind = paged_store._encode_cursor(
        {
            "v": 1,
            "kind": "events",
            "created_at": NOW,
            "job_id": "job-1",
            "project_id": None,
            "state": None,
        }
    )
    bad_job_coordinate = paged_store._encode_cursor(
        {
            "v": 1,
            "kind": "jobs",
            "created_at": 7,
            "job_id": "job-1",
            "project_id": None,
            "state": None,
        }
    )
    bad_job_instant = paged_store._encode_cursor(
        {
            "v": 1,
            "kind": "jobs",
            "created_at": "not-an-instant",
            "job_id": "job-1",
            "project_id": None,
            "state": None,
        }
    )
    for cursor in (wrong_job_version, wrong_job_kind, bad_job_coordinate, bad_job_instant):
        with pytest.raises(ValueError, match="invalid job cursor"):
            paged_store._decode_job_cursor(cursor, project_id=None, state=None)


def test_event_cursor_decoder_rejects_schema_drift_and_invalid_coordinates() -> None:
    run_id = RunId("run-1")
    wrong_version = paged_store._encode_cursor(
        {
            "v": 2,
            "kind": "run-events",
            "run_id": str(run_id),
            "next_sequence": 0,
            "attempt_ordinal": 0,
            "attempt_sequence": -1,
        }
    )
    wrong_kind = paged_store._encode_cursor(
        {
            "v": 1,
            "kind": "jobs",
            "run_id": str(run_id),
            "next_sequence": 0,
            "attempt_ordinal": 0,
            "attempt_sequence": -1,
        }
    )
    invalid_coordinate = paged_store._encode_cursor(
        {
            "v": 1,
            "kind": "run-events",
            "run_id": str(run_id),
            "next_sequence": True,
            "attempt_ordinal": 0,
            "attempt_sequence": -1,
        }
    )
    invalid_sentinel = paged_store._encode_cursor(
        {
            "v": 1,
            "kind": "run-events",
            "run_id": str(run_id),
            "next_sequence": 0,
            "attempt_ordinal": 0,
            "attempt_sequence": 0,
        }
    )
    for cursor in (wrong_version, wrong_kind, invalid_coordinate, invalid_sentinel):
        with pytest.raises(ValueError, match="event cursor"):
            paged_store._decode_event_cursor(cursor, run_id=run_id)


def test_run_event_page_is_dense_across_attempts_and_pollable(store) -> None:
    _create(store, "job-events", NOW)
    first = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=AttemptId("attempt-1"),
        lease_seconds=30,
        now=Instant(NOW),
    )
    assert first is not None
    store.append_events(
        first.attempt_id,
        (
            StoredExecutionEvent(first.attempt_id, 0, "attempt.started", "", NOW),
            StoredExecutionEvent(first.attempt_id, 1, "cell.succeeded", "one", NOW),
        ),
        owner="worker-1",
        lease_token=first.lease_token,
        now=Instant(NOW),
    )
    assert store.reclaim_expired(now=Instant(AFTER_EXPIRY)) == (RunId("run-job-events"),)

    second = store.claim_next_run(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=AttemptId("attempt-2"),
        lease_seconds=30,
        now=Instant(AFTER_EXPIRY),
    )
    assert second is not None
    store.append_events(
        second.attempt_id,
        (
            StoredExecutionEvent(second.attempt_id, 0, "attempt.started", "", AFTER_EXPIRY),
            StoredExecutionEvent(second.attempt_id, 1, "cell.succeeded", "two", AFTER_EXPIRY),
        ),
        owner="worker-2",
        lease_token=second.lease_token,
        now=Instant(AFTER_EXPIRY),
    )

    first_page = store.read_event_page(RunId("run-job-events"), since=None, limit=3)
    assert [event.sequence for event in first_page.items] == [0, 1, 2]
    assert [event.attempt_id for event in first_page.items] == [
        AttemptId("attempt-1"),
        AttemptId("attempt-1"),
        AttemptId("attempt-2"),
    ]
    assert [event.attempt_sequence for event in first_page.items] == [0, 1, 0]

    second_page = store.read_event_page(
        RunId("run-job-events"),
        since=first_page.next_since,
        limit=3,
    )
    assert [event.sequence for event in second_page.items] == [3]
    assert [event.attempt_sequence for event in second_page.items] == [1]

    empty_poll = store.read_event_page(
        RunId("run-job-events"),
        since=second_page.next_since,
        limit=3,
    )
    assert empty_poll.items == ()
    assert empty_poll.next_since == second_page.next_since

    store.append_events(
        second.attempt_id,
        (
            StoredExecutionEvent(
                second.attempt_id, 2, "cell.succeeded", "three", SECOND_ATTEMPT_WRITE
            ),
        ),
        owner="worker-2",
        lease_token=second.lease_token,
        now=Instant(SECOND_ATTEMPT_WRITE),
    )
    resumed_poll = store.read_event_page(
        RunId("run-job-events"),
        since=empty_poll.next_since,
        limit=3,
    )
    assert [event.sequence for event in resumed_poll.items] == [4]
    assert resumed_poll.items[0].attempt_sequence == 2


def test_event_cursor_is_fail_closed_bounded_and_bound_to_run(store) -> None:
    _create(store, "job-events", NOW)
    initial = store.read_event_page(RunId("run-job-events"), since=None, limit=1)

    with pytest.raises(ValueError, match="cursor"):
        store.read_event_page(RunId("run-job-events"), since="%%%", limit=1)
    with pytest.raises(ValueError, match="run"):
        store.read_event_page(RunId("run-other"), since=initial.next_since, limit=1)
    with pytest.raises(ValueError, match="limit"):
        store.read_event_page(RunId("run-job-events"), since=None, limit=101)


def test_bounded_async_store_exposes_event_page_without_blocking_loop() -> None:
    async def exercise() -> None:
        inner = InMemoryJobStore()
        _create(inner, "job-events", NOW)
        async with BoundedAsyncJobStore(inner, max_workers=1, max_in_flight=1) as store:
            page = await store.read_event_page(RunId("run-job-events"), since=None, limit=1)
            assert page.items == ()
            assert page.next_since

    asyncio.run(exercise())


def test_run_execution_event_rejects_negative_coordinates() -> None:
    with pytest.raises(ValueError, match="run event sequence"):
        RunExecutionEvent(
            sequence=-1,
            attempt_id=AttemptId("attempt-1"),
            attempt_sequence=0,
            kind="attempt.started",
            message="",
            occurred_at=NOW,
        )
    with pytest.raises(ValueError, match="attempt event sequence"):
        RunExecutionEvent(
            sequence=0,
            attempt_id=AttemptId("attempt-1"),
            attempt_sequence=-1,
            kind="attempt.started",
            message="",
            occurred_at=NOW,
        )
