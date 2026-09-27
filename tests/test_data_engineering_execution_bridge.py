import pytest

from studio_data_engineering import (
    attach_pipeline_evidence,
    cancel_pipeline,
    pipeline_evidence,
    pipeline_status,
    plan_pipeline_execution,
    submit_pipeline_plan,
)
from studio_execution import DurableExecutionService
from studio_orchestrator import AttemptId, AttemptState, Instant, LeaseToken
from studio_storage import LocalArtifactStore, SqliteJobStore

LEASE_TOKEN = "lease-1"  # noqa: S105 - deterministic test lease token


class FakeDurableService:
    def __init__(self) -> None:
        self.calls = []

    async def submit(self, job, run):
        self.calls.append((job, run))
        return job


@pytest.mark.asyncio
async def test_execution_bridge_submits_job_run_once() -> None:
    plan = plan_pipeline_execution(
        project_id="p",
        revision_key="main/1",
        ir_digest="b" * 64,
        runtime="local-preview",
        now=Instant("2026-09-19T10:00:00.000000Z"),
    )
    service = FakeDurableService()
    result = await submit_pipeline_plan(service, plan)
    assert result["job_id"] == str(plan.job.id)
    assert result["state"] == "queued"
    assert len(service.calls) == 1
    assert service.calls[0][1].job_id == plan.job.id


@pytest.mark.asyncio
async def test_execution_bridge_persists_and_replays_idempotently(tmp_path) -> None:
    plan = plan_pipeline_execution(
        project_id="p",
        revision_key="main/1",
        ir_digest="d" * 64,
        runtime="local-preview",
        now=Instant("2026-09-19T10:00:00.000000Z"),
    )
    store = SqliteJobStore(tmp_path / "jobs.db", migration_now="2026-09-19T10:00:00.000000Z")
    async with DurableExecutionService(store) as service:
        first = await submit_pipeline_plan(service, plan)
        second = await submit_pipeline_plan(service, plan)
    assert first["job_id"] == second["job_id"]
    reopened = SqliteJobStore(tmp_path / "jobs.db", migration_now="2026-09-19T10:00:00.000000Z")
    assert reopened.get_job(plan.job.id) is not None


@pytest.mark.asyncio
async def test_pipeline_job_claim_heartbeat_and_completion(tmp_path) -> None:
    plan = plan_pipeline_execution(
        project_id="p",
        revision_key="main/1",
        ir_digest="e" * 64,
        runtime="local-preview",
        now=Instant("2026-09-19T10:00:00.000000Z"),
    )
    store = SqliteJobStore(tmp_path / "jobs.db", migration_now="2026-09-19T10:00:00.000000Z")
    async with DurableExecutionService(store) as service:
        await submit_pipeline_plan(service, plan)
        claim = await service.worker_poll(
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            attempt_id=AttemptId("attempt-1"),
            lease_seconds=60,
            now=Instant("2026-09-19T10:00:01.000000Z"),
        )
        assert claim.claim is not None
        assert (
            await service.worker_heartbeat(
                claim.claim.attempt_id,
                owner="worker-1",
                lease_token=LeaseToken("lease-1"),
                expires_at=Instant("2026-09-19T10:01:30.000000Z"),
                now=Instant("2026-09-19T10:00:10.000000Z"),
            )
            is True
        )
        await service.worker_complete_attempt(
            claim.claim.attempt_id,
            state=AttemptState.SUCCEEDED,
            failure_code=None,
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            now=Instant("2026-09-19T10:00:20.000000Z"),
        )
        status = await service.status(plan.job.id)
        assert status is not None
        assert status.state.value == "succeeded"


@pytest.mark.asyncio
async def test_pipeline_status_cancel_and_evidence_use_durable_service(tmp_path) -> None:
    plan = plan_pipeline_execution(
        project_id="p",
        revision_key="main/1",
        ir_digest="f" * 64,
        runtime="local-preview",
        now=Instant("2026-09-19T10:00:00.000000Z"),
    )
    store = SqliteJobStore(tmp_path / "jobs.db", migration_now="2026-09-19T10:00:00.000000Z")
    async with DurableExecutionService(store) as service:
        await submit_pipeline_plan(service, plan)
        assert (await pipeline_status(service, str(plan.job.id)))["state"] == "queued"
        assert await pipeline_evidence(service, str(plan.job.id)) == ()
        result = await cancel_pipeline(
            service,
            str(plan.job.id),
            now=Instant("2026-09-19T10:00:01.000000Z"),
        )
        assert result["state"] == "cancelled"


@pytest.mark.asyncio
async def test_worker_output_evidence_is_attached_to_fenced_attempt(tmp_path) -> None:
    plan = plan_pipeline_execution(
        project_id="p",
        revision_key="main/1",
        ir_digest="a" * 64,
        runtime="local-preview",
        now=Instant("2026-09-19T10:00:00.000000Z"),
    )
    store = SqliteJobStore(tmp_path / "jobs.db", migration_now="2026-09-19T10:00:00.000000Z")
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    async with DurableExecutionService(store) as service:
        await submit_pipeline_plan(service, plan)
        claim = await service.worker_poll(
            owner="worker-1",
            lease_token=LeaseToken("lease-1"),
            attempt_id=AttemptId("attempt-1"),
            lease_seconds=60,
            now=Instant("2026-09-19T10:00:01.000000Z"),
        )
        assert claim.claim is not None
        artifact = artifacts.put_bytes(
            role="data-engineering/p/run/preview-evidence.json",
            data=b'{"rows":1}',
            media_type="application/json",
        )
        ref = await attach_pipeline_evidence(
            service,
            artifact,
            run_id=str(plan.run.id),
            attempt_id="attempt-1",
            owner="worker-1",
            lease_token=LEASE_TOKEN,
            now=Instant("2026-09-19T10:00:02.000000Z"),
        )
        evidence = await pipeline_evidence(service, str(plan.job.id))
        assert evidence == (ref,)
        assert ref.storage_ref == artifact.storage_ref
        assert ref.digest == artifact.digest
