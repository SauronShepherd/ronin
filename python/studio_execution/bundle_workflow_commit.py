"""Atomic commit application service for native workflow/schedule Bundle imports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio_core import Schedule, WorkflowDefinition, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.bundle import BundleReadLimits
from studio_storage.bundle_workflow_import_port import (
    WorkflowBundleImportCommit,
    WorkflowBundleImportConflict,
    WorkflowBundleImportStore,
)

from .bundle_workflow import WorkflowBundleImportPlan, plan_workflow_bundle_import


@dataclass(frozen=True, slots=True)
class WorkflowBundleImportOutcome:
    plan: WorkflowBundleImportPlan
    commit: WorkflowBundleImportCommit


def commit_workflow_bundle_import(
    bundle_path: Path,
    store: WorkflowBundleImportStore,
    workspace_id: WorkspaceId,
    *,
    now: Instant | str,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 16 * 1024 * 1024,
) -> WorkflowBundleImportOutcome:
    """Re-plan verified bytes, then atomically commit portable scheduler definitions."""

    plan = plan_workflow_bundle_import(
        bundle_path,
        store,
        store,
        workspace_id,
        limits=limits,
        max_inventory_bytes=max_inventory_bytes,
        max_object_bytes=max_object_bytes,
    )
    collisions = [item for item in plan.objects if item.disposition == "collision"]
    if collisions:
        raise WorkflowBundleImportConflict(
            collisions[0].collision_reason or "workflow Bundle import collision"
        )

    workflows: list[WorkflowDefinition] = []
    schedules: list[Schedule] = []
    for item in plan.objects:
        if item.kind == "workflow":
            if not isinstance(item.payload, WorkflowDefinition):
                raise TypeError("staged workflow payload has unexpected type")
            workflows.append(item.payload)
        elif item.kind == "schedule":
            if not isinstance(item.payload, Schedule):
                raise TypeError("staged schedule payload has unexpected type")
            schedules.append(item.payload)
        else:
            raise AssertionError(f"unsupported staged workflow object kind: {item.kind}")

    commit = store.commit_workflow_import(
        workspace_id,
        tuple(workflows),
        tuple(schedules),
        now=now,
    )
    return WorkflowBundleImportOutcome(plan, commit)


__all__ = ("WorkflowBundleImportOutcome", "commit_workflow_bundle_import")
