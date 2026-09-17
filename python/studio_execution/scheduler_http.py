"""SQLite adapter for the local workflow HTTP contract."""

from __future__ import annotations

import hashlib
from typing import Protocol

from studio_core import (
    TaskRun,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRun,
    WorkflowRunId,
    WorkspaceId,
)
from studio_orchestrator import Instant


class WorkflowStore(Protocol):
    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]: ...

    def get_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> WorkflowRun | None: ...

    def list_task_runs(
        self, workspace_id: WorkspaceId, run_id: WorkflowRunId
    ) -> tuple[TaskRun, ...]: ...

    def create_run(
        self,
        workspace_id: WorkspaceId,
        run_id: WorkflowRunId,
        workflow_id: WorkflowId,
        trigger: Trigger,
        *,
        now: Instant | str,
    ) -> WorkflowRun: ...


class SqliteWorkflowHTTPAdapter:
    """Expose the existing durable SQLite scheduler store to the HTTP server."""

    def __init__(self, store: WorkflowStore, *, now: Instant | str) -> None:
        self._store = store
        self._now = Instant(now)

    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]:
        return self._store.list_workflows(workspace_id)

    def get_run(self, workspace_id: WorkspaceId, run_id: WorkflowRunId) -> WorkflowRun | None:
        return self._store.get_run(workspace_id, run_id)

    def list_task_runs(
        self, workspace_id: WorkspaceId, run_id: WorkflowRunId
    ) -> tuple[TaskRun, ...]:
        return self._store.list_task_runs(workspace_id, run_id)

    def create_workflow_run(
        self,
        workspace_id: WorkspaceId,
        workflow_id: WorkflowId,
        trigger: Trigger,
        *,
        idempotency_key: str,
    ) -> WorkflowRun:
        if not idempotency_key or idempotency_key != idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty and trimmed")
        api_trigger = Trigger("api", idempotency_key, trigger.source_ref)
        material = f"{workspace_id}\0{workflow_id}\0{idempotency_key}".encode()
        run_id = WorkflowRunId("run-" + hashlib.sha256(material).hexdigest()[:32])
        return self._store.create_run(
            workspace_id,
            run_id,
            workflow_id,
            api_trigger,
            now=self._now,
        )


__all__ = ("SqliteWorkflowHTTPAdapter", "WorkflowStore")
