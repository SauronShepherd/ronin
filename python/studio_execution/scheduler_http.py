"""SQLite adapter for the local workflow HTTP contract."""

from __future__ import annotations

import hashlib
from typing import Protocol

from studio_core import (
    Schedule,
    ScheduleId,
    TaskRun,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRun,
    WorkflowRunId,
    WorkspaceId,
)
from studio_core.scheduler_events import EventTriggerDefinition, SchedulerEventId
from studio_orchestrator import Instant
from studio_storage.scheduler_backfill import BackfillId, BackfillRequest
from studio_storage.scheduler_events import EventDelivery, SchedulerEventRecord
from studio_storage.scheduler_schedule import ScheduleFire

from .scheduler_backfill import preview_backfill
from .scheduler_schedule_service import SchedulerScheduleService


class WorkflowStore(Protocol):
    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]: ...

    def put_workflow(
        self, workspace_id: WorkspaceId, workflow: WorkflowDefinition, *, now: Instant | str
    ) -> WorkflowDefinition: ...

    def list_schedules(self, workspace_id: WorkspaceId) -> tuple[Schedule, ...]: ...

    def get_schedule(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> Schedule | None: ...

    def put_schedule(
        self, workspace_id: WorkspaceId, schedule: Schedule, *, now: Instant | str
    ) -> Schedule: ...

    def preview_schedule_next_runs(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        after: Instant | str,
        count: int = 10,
    ) -> tuple[Instant, ...]: ...

    def list_schedule_fires(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> tuple[ScheduleFire, ...]: ...

    def get_event(
        self, workspace_id: WorkspaceId, event_id: SchedulerEventId
    ) -> SchedulerEventRecord | None: ...

    def list_event_triggers(
        self, workspace_id: WorkspaceId
    ) -> tuple[EventTriggerDefinition, ...]: ...

    def put_event_trigger(
        self, workspace_id: WorkspaceId, trigger: EventTriggerDefinition, *, now: Instant | str
    ) -> EventTriggerDefinition: ...

    def ingest_event(self, event: SchedulerEventRecord) -> tuple[EventDelivery, ...]: ...

    def list_pending_deliveries(
        self, workspace_id: WorkspaceId, *, limit: int = 100
    ) -> tuple[EventDelivery, ...]: ...

    def preview_backfill(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        start_at: Instant | str,
        end_at: Instant | str,
        max_runs: int = 1000,
    ) -> tuple[Instant, ...]: ...

    def create_backfill(
        self, workspace_id: WorkspaceId, request: BackfillRequest, *, now: Instant | str
    ) -> BackfillRequest: ...

    def get_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillRequest | None: ...

    def cancel_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId, *, now: Instant | str
    ) -> BackfillRequest: ...

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

    def put_workflow(
        self, workspace_id: WorkspaceId, workflow: WorkflowDefinition
    ) -> WorkflowDefinition:
        return self._store.put_workflow(workspace_id, workflow, now=self._now)

    def list_schedules(self, workspace_id: WorkspaceId) -> tuple[Schedule, ...]:
        return self._store.list_schedules(workspace_id)

    def get_schedule(self, workspace_id: WorkspaceId, schedule_id: ScheduleId) -> Schedule | None:
        return self._store.get_schedule(workspace_id, schedule_id)

    def put_schedule(self, workspace_id: WorkspaceId, schedule: Schedule) -> Schedule:
        return self._store.put_schedule(workspace_id, schedule, now=self._now)

    def preview_schedule_next_runs(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        after: Instant | str,
        count: int = 10,
    ) -> tuple[Instant, ...]:
        schedule = self._store.get_schedule(workspace_id, schedule_id)
        if schedule is None:
            raise LookupError("schedule does not exist")
        return SchedulerScheduleService.preview_next_runs(schedule, after=after, count=count)

    def list_schedule_fires(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> tuple[ScheduleFire, ...]:
        return self._store.list_schedule_fires(workspace_id, schedule_id)

    def get_event(
        self, workspace_id: WorkspaceId, event_id: SchedulerEventId
    ) -> SchedulerEventRecord | None:
        return self._store.get_event(workspace_id, event_id)

    def list_pending_deliveries(
        self, workspace_id: WorkspaceId, *, limit: int = 100
    ) -> tuple[EventDelivery, ...]:
        return self._store.list_pending_deliveries(workspace_id, limit=limit)

    def preview_backfill(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        start_at: Instant | str,
        end_at: Instant | str,
        max_runs: int = 1000,
    ) -> tuple[Instant, ...]:
        schedule = self._store.get_schedule(workspace_id, schedule_id)
        if schedule is None:
            raise LookupError("schedule does not exist")
        return preview_backfill(schedule, start_at=start_at, end_at=end_at, max_runs=max_runs)

    def list_event_triggers(self, workspace_id: WorkspaceId) -> tuple[EventTriggerDefinition, ...]:
        return self._store.list_event_triggers(workspace_id)

    def put_event_trigger(
        self, workspace_id: WorkspaceId, trigger: EventTriggerDefinition
    ) -> EventTriggerDefinition:
        return self._store.put_event_trigger(workspace_id, trigger, now=self._now)

    def ingest_event(self, event: SchedulerEventRecord) -> tuple[EventDelivery, ...]:
        return self._store.ingest_event(event)

    def create_backfill(
        self, workspace_id: WorkspaceId, request: BackfillRequest
    ) -> BackfillRequest:
        return self._store.create_backfill(workspace_id, request, now=self._now)

    def get_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillRequest | None:
        return self._store.get_backfill(workspace_id, backfill_id)

    def cancel_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillRequest:
        return self._store.cancel_backfill(workspace_id, backfill_id, now=self._now)

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
