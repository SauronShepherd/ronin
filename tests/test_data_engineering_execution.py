from studio_data_engineering import plan_pipeline_execution
from studio_orchestrator import Instant, JobState, RunState


def test_pipeline_execution_plan_is_deterministic() -> None:
    kwargs = {
        "project_id": "project-1",
        "revision_key": "pipeline/main/1",
        "ir_digest": "a" * 64,
        "runtime": "spark-connect",
        "parameters": {"date": "2026-09-19"},
        "now": Instant("2026-09-19T10:00:00.000000Z"),
    }
    first = plan_pipeline_execution(**kwargs)
    second = plan_pipeline_execution(**kwargs)
    assert first.job.id == second.job.id
    assert first.run.id == second.run.id
    assert first.job.state is JobState.QUEUED
    assert first.run.state is RunState.PENDING
    assert first.job.target == "data-engineering.pipeline-run.v1"
