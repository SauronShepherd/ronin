from __future__ import annotations

import os
from uuid import uuid4

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
from studio_storage import PostgresJobReadPort, PostgresMetadataStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL qualification requires RONIN_POSTGRES_TEST_DSN",
)

NOW = Instant("2026-09-16T09:00:00.000000Z")


def test_postgres_jobstore_complete_lifecycle() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    PostgresMetadataStore(dsn, application_name="ronin-qualification")
    store = PostgresJobReadPort(dsn, application_name="ronin-qualification")
    suffix = uuid4().hex
    job_id = JobId(f"job-pg-{suffix}")
    run_id = RunId(f"run-pg-{suffix}")
    job = Job(
        id=job_id,
        project_id="project-pg-qualification",
        idempotency_key=f"key-{suffix}",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=NOW,
        updated_at=NOW,
    )
    run = Run(
        id=run_id,
        job_id=job_id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    store.create_job(job, run)
    claim = store.claim_next_run(
        owner="qualification",
        lease_token=LeaseToken(f"lease-{suffix}"),
        attempt_id=AttemptId(f"attempt-{suffix}"),
        lease_seconds=30,
        now=NOW,
    )
    assert claim is not None
    owner = "qualification"
    lease_token = claim.lease_token
    store.append_events(
        claim.attempt_id,
        (StoredExecutionEvent(claim.attempt_id, 0, "run.started", "ok", NOW),),
        owner=owner,
        lease_token=lease_token,
        now=NOW,
    )
    store.put_cell_result(
        claim.attempt_id,
        StoredCellResult(run_id, "cell-1", "b" * 64, "c" * 64, "succeeded", "{}", NOW),
        owner=owner,
        lease_token=lease_token,
        now=NOW,
    )
    store.put_evidence(
        claim.attempt_id,
        StoredEvidenceRef(
            run_id, "cell-1", "stdout", "sha256", "d" * 64, "text/plain", 2, "local://evidence"
        ),
        owner=owner,
        lease_token=lease_token,
        now=NOW,
    )
    store.complete_attempt(
        claim.attempt_id,
        state=AttemptState.SUCCEEDED,
        failure_code=None,
        owner=owner,
        lease_token=lease_token,
        now=NOW,
    )
    completed_job = store.get_job(job_id)
    assert completed_job is not None
    assert completed_job.state is JobState.SUCCEEDED
    assert len(store.read_events(run_id, since=0)) == 1
    assert len(store.read_cell_results(run_id)) == 1
    assert len(store.read_evidence(run_id)) == 1
