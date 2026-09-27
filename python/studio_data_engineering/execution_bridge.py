"""Async bridge from Data Enginerring execution plans to Ronin Jobs."""

from __future__ import annotations

from typing import Protocol

from studio_orchestrator import (
    AttemptId,
    EvidenceAvailability,
    Instant,
    Job,
    JobId,
    LeaseToken,
    RunId,
    StoredEvidenceRef,
)
from studio_storage import ArtifactRef

from .execution import PipelineExecutionPlan


class DurableSubmitter(Protocol):
    async def submit(self, job: Job, run: object) -> Job: ...

    async def status(self, job_id: JobId) -> Job | None: ...

    async def cancel(self, job_id: JobId, *, now: Instant) -> Job: ...

    async def evidence(self, job_id: JobId) -> tuple[StoredEvidenceRef, ...] | None: ...

    async def worker_put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...


async def submit_pipeline_plan(
    service: DurableSubmitter,
    plan: PipelineExecutionPlan,
) -> dict[str, object]:
    """Submit one deterministic plan through the shared durable execution port."""
    stored = await service.submit(plan.job, plan.run)
    return {
        "job_id": str(stored.id),
        "project_id": stored.project_id,
        "state": stored.state.value,
        "target": stored.target,
        "request_digest": stored.request_digest,
        "revision_key": plan.revision_key,
    }


async def pipeline_status(service: DurableSubmitter, job_id: str) -> dict[str, object] | None:
    status = await service.status(JobId(job_id))
    if status is None:
        return None
    return {
        "job_id": str(status.id),
        "state": status.state.value,
        "failure_code": status.failure_code,
    }


async def cancel_pipeline(
    service: DurableSubmitter, job_id: str, *, now: Instant
) -> dict[str, object]:
    status = await service.cancel(JobId(job_id), now=now)
    return {"job_id": str(status.id), "state": status.state.value}


async def pipeline_evidence(service: DurableSubmitter, job_id: str) -> tuple[object, ...] | None:
    return await service.evidence(JobId(job_id))


async def attach_pipeline_evidence(
    service: DurableSubmitter,
    artifact: ArtifactRef,
    *,
    run_id: str,
    attempt_id: str,
    owner: str,
    lease_token: str,
    now: Instant,
    cell_id: str = "pipeline",
) -> StoredEvidenceRef:
    """Attach worker-produced content-addressed evidence to a fenced attempt."""
    ref = StoredEvidenceRef(
        run_id=RunId(run_id),
        cell_id=cell_id,
        role="output",
        digest_algorithm=artifact.digest_algorithm,
        digest=artifact.digest,
        media_type=artifact.media_type,
        size_bytes=artifact.size_bytes,
        storage_ref=artifact.storage_ref,
        availability=EvidenceAvailability.AVAILABLE,
    )
    await service.worker_put_evidence(
        AttemptId(attempt_id),
        ref,
        owner=owner,
        lease_token=LeaseToken(lease_token),
        now=now,
    )
    return ref


__all__ = (
    "DurableSubmitter",
    "attach_pipeline_evidence",
    "cancel_pipeline",
    "pipeline_evidence",
    "pipeline_status",
    "submit_pipeline_plan",
)
