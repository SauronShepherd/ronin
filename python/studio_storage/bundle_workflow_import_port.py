"""Provider-neutral atomic commit port for native workflow Bundle imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core import Schedule, ScheduleId, WorkflowDefinition, WorkflowId, WorkspaceId
from studio_orchestrator import Instant

from .ports import WorkspaceStore


class WorkflowBundleImportConflict(RuntimeError):
    """Raised when target scheduler definitions conflict with a Bundle import."""


@dataclass(frozen=True, slots=True)
class WorkflowBundleImportCommit:
    workflows_created: int
    schedules_created: int


@runtime_checkable
class SchedulerDefinitionStore(Protocol):
    """Portable workflow/schedule definition boundary without runtime scheduler state."""

    def get_workflow(
        self,
        workspace_id: WorkspaceId,
        workflow_id: WorkflowId,
    ) -> WorkflowDefinition | None: ...

    def list_workflows(
        self,
        workspace_id: WorkspaceId,
    ) -> tuple[WorkflowDefinition, ...]: ...

    def get_schedule(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
    ) -> Schedule | None: ...

    def list_schedules(
        self,
        workspace_id: WorkspaceId,
    ) -> tuple[Schedule, ...]: ...


@runtime_checkable
class WorkflowBundleImportStore(WorkspaceStore, SchedulerDefinitionStore, Protocol):
    """Scheduler definition boundary that atomically commits portable intent."""

    def commit_workflow_import(
        self,
        workspace_id: WorkspaceId,
        workflows: tuple[WorkflowDefinition, ...],
        schedules: tuple[Schedule, ...],
        *,
        now: Instant | str,
    ) -> WorkflowBundleImportCommit: ...


__all__ = (
    "SchedulerDefinitionStore",
    "WorkflowBundleImportCommit",
    "WorkflowBundleImportConflict",
    "WorkflowBundleImportStore",
)
