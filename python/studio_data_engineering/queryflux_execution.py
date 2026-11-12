"""Deterministic durable-job identity for asynchronous QueryFlux execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState


@dataclass(frozen=True, slots=True)
class QueryFluxExecutionPlan:
    """The idempotent job/run pair persisted before worker dispatch."""

    workspace_id: str
    project_id: str
    run_id: str
    attempt_id: str
    job: Job
    run: Run


def plan_queryflux_execution(
    *,
    workspace_id: str,
    project_id: str,
    run_id: str,
    attempt_id: str,
    sql: str,
    engine: str,
    translation_policy: str,
    max_rows: int,
    page_size: int,
    max_result_bytes: int,
    parameters: list[object] | None = None,
    now: Instant | str,
) -> QueryFluxExecutionPlan:
    values = (workspace_id, project_id, run_id, attempt_id, sql, engine, translation_policy)
    if any(not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value for value in values):
        raise ValueError("QueryFlux execution identifiers and SQL must be non-empty single-line text")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in (max_rows, page_size, max_result_bytes)
    ):
        raise ValueError("QueryFlux execution limits must be positive integers")
    payload = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "sql": sql,
        "engine": engine,
        "translation_policy": translation_policy,
        "max_rows": max_rows,
        "page_size": page_size,
        "max_result_bytes": max_result_bytes,
        "parameters": list(parameters or []),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    current = Instant(now)
    job_id = JobId(f"job-queryflux-{digest[:32]}")
    durable_run_id = RunId(f"run-queryflux-{digest[:32]}")
    job = Job(
        id=job_id,
        project_id=project_id,
        idempotency_key=f"queryflux:{workspace_id}:{project_id}:{run_id}:{attempt_id}",
        request_digest=digest,
        state=JobState.QUEUED,
        created_at=current,
        updated_at=current,
        target="data-engineering.queryflux-execution.v1",
        parameters_json=encoded.decode(),
    )
    run = Run(
        id=durable_run_id,
        job_id=job_id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=current,
        created_at=current,
        updated_at=current,
    )
    return QueryFluxExecutionPlan(workspace_id, project_id, run_id, attempt_id, job, run)


__all__ = ("QueryFluxExecutionPlan", "plan_queryflux_execution")
