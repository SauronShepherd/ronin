import json
import sqlite3
from concurrent.futures import Future

from studio_synthetic_data import ColumnSpec, GenerationPlan, TableSpec, async_generation
from studio_synthetic_data.application import GovernStudioService, _plan_payload
from studio_synthetic_data.async_generation import LocalGenerationJobs


def _plan() -> GenerationPlan:
    return GenerationPlan((TableSpec("t", (ColumnSpec("id", "integer"),), rows=1),), seed=3)


def test_completed_async_job_state_survives_facade_restart(tmp_path) -> None:
    database = str(tmp_path / "jobs.db")
    first = LocalGenerationJobs(GovernStudioService(), db_path=database)
    submitted = first.submit(_plan(), idempotency_key="async-1")
    first.get(submitted.job_id)
    first.close()
    second = LocalGenerationJobs(GovernStudioService(), db_path=database)
    assert second.get(submitted.job_id).status == "completed"
    second.close()


def test_recovery_commits_queued_state_before_dispatch(tmp_path, monkeypatch) -> None:
    database = str(tmp_path / "queued.db")
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE synthetic_jobs ("
        "job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, plan_json TEXT NOT NULL, "
        "status TEXT NOT NULL, error TEXT, lease_owner TEXT, "
        "lease_epoch INTEGER NOT NULL DEFAULT 0, lease_expires_at REAL)"
    )
    connection.execute(
        "INSERT INTO synthetic_jobs("
        "job_id,run_id,plan_json,status,lease_owner,lease_epoch,lease_expires_at) "
        "VALUES(?,?,?,?,?,?,?)",
        ("recovered-job", "run-1", json.dumps(_plan_payload(_plan())), "running", "old", 1, 0),
    )
    connection.commit()
    connection.close()

    observed_statuses: list[str] = []

    class RecordingExecutor:
        def __init__(self, **_kwargs) -> None:
            pass

        def submit(self, _function, *_args):
            with sqlite3.connect(database) as observer:
                status = observer.execute(
                    "SELECT status FROM synthetic_jobs WHERE job_id='recovered-job'"
                ).fetchone()[0]
            observed_statuses.append(status)
            future: Future[None] = Future()
            future.set_result(None)
            return future

        def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
            del wait, cancel_futures

    monkeypatch.setattr(async_generation, "ThreadPoolExecutor", RecordingExecutor)
    jobs = LocalGenerationJobs(GovernStudioService(), db_path=database)
    try:
        assert jobs.get("recovered-job").status == "queued"
        assert observed_statuses == ["queued"]
    finally:
        jobs.close()


def test_cancel_of_terminal_job_is_safe(tmp_path) -> None:
    jobs = LocalGenerationJobs(GovernStudioService(), db_path=str(tmp_path / "cancel.db"))
    submitted = jobs.submit(_plan(), idempotency_key="cancel-1")
    jobs.get(submitted.job_id)
    jobs.close()
    reopened = LocalGenerationJobs(GovernStudioService(), db_path=str(tmp_path / "cancel.db"))
    assert reopened.cancel(submitted.job_id).status == "completed"
    reopened.close()
