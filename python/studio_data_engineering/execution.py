"""Translate a validated pipeline revision into Ronin Job/Run contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState


@dataclass(frozen=True, slots=True)
class PipelineExecutionPlan:
    revision_key: str
    job: Job
    run: Run


def plan_pipeline_execution(
    *,
    project_id: str,
    revision_key: str,
    ir_digest: str,
    runtime: str,
    parameters: Mapping[str, object] | None = None,
    now: Instant | str,
) -> PipelineExecutionPlan:
    if not project_id.strip() or "\n" in project_id or "\r" in project_id:
        raise ValueError("project_id must be non-empty and single-line")
    if not revision_key.strip() or "\n" in revision_key or "\r" in revision_key:
        raise ValueError("revision_key must be non-empty and single-line")
    if not ir_digest.strip() or len(ir_digest) != 64:
        raise ValueError("ir_digest must be a sha256 hex digest")
    if not runtime.strip():
        raise ValueError("runtime must be non-empty")
    current = Instant(now)
    payload = {
        "project_id": project_id,
        "revision_key": revision_key,
        "ir_digest": ir_digest,
        "runtime": runtime,
        "parameters": dict(parameters or {}),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    job_id = JobId(f"job-data-engineering-{digest[:32]}")
    run_id = RunId(f"run-data-engineering-{digest[:32]}")
    job = Job(
        id=job_id,
        project_id=project_id,
        idempotency_key=f"data-engineering:{revision_key}:{runtime}:{digest}",
        request_digest=digest,
        state=JobState.QUEUED,
        created_at=current,
        updated_at=current,
        target="data-engineering.pipeline-run.v1",
        parameters_json=encoded.decode(),
    )
    run = Run(
        id=run_id,
        job_id=job_id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=current,
        created_at=current,
        updated_at=current,
    )
    return PipelineExecutionPlan(revision_key, job, run)


__all__ = ("PipelineExecutionPlan", "plan_pipeline_execution")
