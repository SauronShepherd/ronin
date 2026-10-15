from studio_synthetic_data import ColumnSpec, GenerationPlan, TableSpec
from studio_synthetic_data.application import GovernStudioService
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


def test_cancel_of_terminal_job_is_safe(tmp_path) -> None:
    jobs = LocalGenerationJobs(GovernStudioService(), db_path=str(tmp_path / "cancel.db"))
    submitted = jobs.submit(_plan(), idempotency_key="cancel-1")
    jobs.get(submitted.job_id)
    jobs.close()
    reopened = LocalGenerationJobs(GovernStudioService(), db_path=str(tmp_path / "cancel.db"))
    assert reopened.cancel(submitted.job_id).status == "completed"
    reopened.close()
