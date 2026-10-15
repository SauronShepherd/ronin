from __future__ import annotations

import pytest
from studio_orchestrator import Instant, JobId, JobState, RunId
from studio_storage import paged_store
from studio_storage.pagination import (
    decode_cursor,
    decode_event_cursor,
    decode_job_cursor,
    encode_cursor,
    encode_event_cursor,
    encode_job_cursor,
    initial_event_cursor,
    validate_limit,
)

NOW = Instant("2026-09-07T09:00:00.000000Z")


def test_paged_store_private_cursor_aliases_delegate_to_canonical_helpers() -> None:
    assert paged_store._encode_cursor is encode_cursor
    assert paged_store._decode_cursor is decode_cursor
    assert paged_store._encode_job_cursor is encode_job_cursor
    assert paged_store._decode_job_cursor is decode_job_cursor
    assert paged_store._encode_event_cursor is encode_event_cursor
    assert paged_store._decode_event_cursor is decode_event_cursor
    assert paged_store._initial_event_cursor is initial_event_cursor
    assert paged_store._validate_limit is validate_limit


def test_job_cursor_round_trip_is_bound_to_filters() -> None:
    cursor = encode_job_cursor(
        created_at=NOW,
        job_id=JobId("job-1"),
        project_id="project-1",
        state=JobState.QUEUED,
    )
    assert decode_job_cursor(
        cursor,
        project_id="project-1",
        state=JobState.QUEUED,
    ) == (NOW, JobId("job-1"))
    with pytest.raises(ValueError, match="filters"):
        decode_job_cursor(cursor, project_id="project-2", state=JobState.QUEUED)


def test_event_cursor_round_trip_is_bound_to_run_and_dense_coordinate() -> None:
    run_id = RunId("run-1")
    initial = initial_event_cursor(run_id)
    assert decode_event_cursor(initial, run_id=run_id) == (0, 0, -1)

    cursor = encode_event_cursor(
        run_id=run_id,
        next_sequence=7,
        attempt_ordinal=2,
        attempt_sequence=3,
    )
    assert decode_event_cursor(cursor, run_id=run_id) == (7, 2, 3)
    with pytest.raises(ValueError, match="run"):
        decode_event_cursor(cursor, run_id=RunId("run-2"))


def test_cursor_and_limit_validation_fail_closed() -> None:
    with pytest.raises(ValueError, match="invalid cursor"):
        decode_cursor("")
    with pytest.raises(ValueError, match="invalid cursor"):
        decode_cursor("x" * 1025)
    for limit in (0, 101):
        with pytest.raises(ValueError, match="limit"):
            validate_limit(limit)
