from pathlib import Path

import pytest
from studio_orchestrator import (
    AttemptId,
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
from studio_storage import SqliteJobStore

NOW = "2026-09-09T16:00:00.000000Z"


def _store(tmp_path: Path) -> tuple[SqliteJobStore, AttemptId]:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=NOW)
    job = Job(
        id=JobId("job-legacy-fence"),
        project_id="project-1",
        idempotency_key="legacy-fence",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )
    run = Run(
        id=RunId("run-legacy-fence"),
        job_id=job.id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    store.create_job(job, run)
    attempt_id = AttemptId("attempt-legacy-fence")
    claim = store.claim_next_run(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=attempt_id,
        lease_seconds=30,
        now=NOW,
    )
    assert claim is not None
    return store, attempt_id


def test_legacy_unfenced_sqlite_write_shapes_fail_closed(tmp_path: Path) -> None:
    store, attempt_id = _store(tmp_path)
    run_id = RunId("run-legacy-fence")
    event = StoredExecutionEvent(attempt_id, 0, "cell.succeeded", "", NOW)
    result = StoredCellResult(
        run_id,
        "cell-1",
        "b" * 64,
        "c" * 64,
        "succeeded",
        "{}",
        NOW,
    )
    evidence = StoredEvidenceRef(
        run_id,
        "cell-1",
        "log",
        "sha256",
        "d" * 64,
        "text/plain",
        0,
        "artifact://sha256/" + "d" * 64,
    )

    with pytest.raises(ValueError, match="active lease"):
        store.append_events(attempt_id, (event,))
    with pytest.raises(ValueError, match="active lease"):
        store.put_cell_result(result)
    with pytest.raises(ValueError, match="active lease"):
        store.put_evidence(evidence)

    assert store.read_events(run_id, since=0) == ()
    assert store.read_cell_results(run_id) == ()
    assert store.read_evidence(run_id) == ()
