"""Deterministic durable-job identity for asynchronous QueryFlux execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState
from studio_query_engine import QueryRequest, TranslationPolicy

from .evidence import EvidenceStore
from .query_execution import QueryEvidenceReferenceStore, execute_query
from .queryflux_lifecycle import QueryFluxExecution, QueryFluxState
from .runtimes import QueryEngineRuntimeProvider


@dataclass(frozen=True, slots=True)
class QueryFluxExecutionPlan:
    """The idempotent job/run pair persisted before worker dispatch."""

    workspace_id: str
    project_id: str
    run_id: str
    attempt_id: str
    job: Job
    run: Run


class QueryFluxWorkerRunner:
    """Execute one persisted QueryFlux payload with durable lifecycle updates."""

    def __init__(
        self,
        provider: QueryEngineRuntimeProvider,
        transport: Any,
        evidence_store: EvidenceStore,
        evidence_reference_store: QueryEvidenceReferenceStore,
        execution_store: Any,
        *,
        artifact_reference_barrier: Any | None = None,
    ) -> None:
        self.provider = provider
        self.transport = transport
        self.evidence_store = evidence_store
        self.evidence_reference_store = evidence_reference_store
        self.execution_store = execution_store
        self.artifact_reference_barrier = artifact_reference_barrier

    def __call__(
        self,
        payload: dict[str, object],
        *,
        cancellation_requested: Callable[[], bool] | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        del run_id
        workspace_id = str(payload["workspace_id"])
        project_id = str(payload["project_id"])
        logical_run_id = str(payload["run_id"])
        attempt_id = str(payload["attempt_id"])
        execution = self.execution_store.create(
            QueryFluxExecution(workspace_id, project_id, logical_run_id, attempt_id)
        )
        if execution.state == "queued":
            execution = self.execution_store.transition(execution.transition("running"))

        def cancelled() -> bool:
            current = self.execution_store.get(workspace_id, project_id, logical_run_id, attempt_id)
            return bool(cancellation_requested and cancellation_requested()) or bool(
                current and current.cancel_requested
            )

        translation_policy = cast(
            TranslationPolicy, str(payload.get("translation_policy", "native_only"))
        )
        parameters = tuple(cast(list[object], payload.get("parameters", [])))
        request = QueryRequest(
            str(payload["sql"]),
            "queryflux",
            translation_policy,
            int(cast(str | int, payload.get("max_rows", 1_000))),
            parameters,
            max_result_bytes=int(
                cast(str | int, payload.get("max_result_bytes", 64 * 1024 * 1024))
            ),
        )
        try:
            result = execute_query(
                self.provider,
                self.transport,
                self.evidence_store,
                request,
                engine=str(payload["engine"]),
                project_id=project_id,
                run_id=logical_run_id,
                attempt_id=attempt_id,
                evidence_reference_store=self.evidence_reference_store,
                artifact_reference_barrier=self.artifact_reference_barrier,
                page_size=int(cast(str | int, payload.get("page_size", 1_000))),
                cancellation_requested=cancelled,
            )
        except Exception as error:
            current = (
                self.execution_store.get(workspace_id, project_id, logical_run_id, attempt_id)
                or execution
            )
            if not current.terminal:
                self.execution_store.transition(
                    current.transition("failed", failure_code=type(error).__name__)
                )
            raise
        current = (
            self.execution_store.get(workspace_id, project_id, logical_run_id, attempt_id)
            or execution
        )
        target: QueryFluxState = (
            "succeeded"
            if result.status.state == "succeeded"
            else "cancelled"
            if result.status.state == "cancelled"
            else "failed"
        )
        if not current.terminal:
            self.execution_store.transition(
                current.transition(
                    target,
                    failure_code=None
                    if target != "failed"
                    else (result.status.message or "query_failed"),
                )
            )
        return {
            "state": result.status.state,
            "row_count": result.row_count,
            "next_cursor": result.next_cursor,
            "selected_engine": result.selected_engine,
            "evidence": {
                "digest": result.evidence_artifact.digest,
                "storage_ref": result.evidence_artifact.storage_ref,
            },
        }


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
    if any(
        not isinstance(value, str) or not value.strip() or "\n" in value or "\r" in value
        for value in values
    ):
        raise ValueError(
            "QueryFlux execution identifiers and SQL must be non-empty single-line text"
        )
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
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
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


__all__ = ("QueryFluxExecutionPlan", "QueryFluxWorkerRunner", "plan_queryflux_execution")
