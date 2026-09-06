from __future__ import annotations

import pytest
from studio_orchestrator import Job, JobId, JobState

NOW = "2026-09-06T09:00:00.000000Z"
LATER = "2026-09-06T09:00:01.000000Z"


def _job(*, target: str = "notebooks/etl", parameters_json: str = "{\"limit\":10}") -> Job:
    return Job(
        id=JobId("job-1"),
        project_id="examples/demo",
        idempotency_key="key-1",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
        target=target,
        parameters_json=parameters_json,
    )


def test_job_keeps_target_and_parameters_across_transition() -> None:
    job = _job()
    running = job.transition(JobState.RUNNING, now=LATER)
    assert running.target == "notebooks/etl"
    assert running.parameters_json == '{"limit":10}'


def test_empty_target_remains_backward_compatible_for_existing_persisted_jobs() -> None:
    assert _job(target="").target == ""


def test_job_rejects_invalid_target_and_parameters_json() -> None:
    with pytest.raises(ValueError, match="target"):
        _job(target=" bad")
    with pytest.raises(ValueError, match="valid JSON"):
        _job(parameters_json="{")
    with pytest.raises(ValueError, match="JSON object"):
        _job(parameters_json="[]")
