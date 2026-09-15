"""Deterministic Ronin Bundle export for workflow and schedule definitions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from studio_core import Schedule, WorkflowDefinition, WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import BundleFile, BundleIntegrityError, BundleReadLimits, write_bundle
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.bundle_workflow_import_port import SchedulerDefinitionStore

WORKFLOW_MEDIA_TYPE = "application/vnd.ronin.workflow+json"
SCHEDULE_MEDIA_TYPE = "application/vnd.ronin.schedule+json"
INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"


@dataclass(frozen=True, slots=True)
class WorkflowBundleInventory:
    inventory: BundleInventory
    files: tuple[BundleFile, ...]


@dataclass(frozen=True, slots=True)
class WorkflowBundleImportPlan:
    """Verified, non-mutating workflow definitions ready for atomic commit."""

    manifest_digest: str
    objects: tuple[StagedWorkflowObject, ...]

    @property
    def has_collisions(self) -> bool:
        return any(item.disposition == "collision" for item in self.objects)


@dataclass(frozen=True, slots=True)
class StagedWorkflowObject:
    kind: str
    logical_ref: str
    payload: WorkflowDefinition | Schedule
    disposition: str
    collision_reason: str | None = None


def _ref(prefix: str, value: str) -> str:
    return f"workflow-{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _path(kind: str, logical_ref: str) -> str:
    digest = hashlib.sha256(logical_ref.encode("utf-8")).hexdigest()
    return f"objects/workflows/{kind}/{digest}.json"


def build_workflow_bundle_inventory(
    store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    workflow_ids: tuple[object, ...] | None = None,
) -> WorkflowBundleInventory:
    """Build a deterministic definition-only inventory for one workspace."""
    all_workflows = tuple(
        sorted(store.list_workflows(workspace_id), key=lambda item: item.id.value)
    )
    selected = set(workflow_ids) if workflow_ids is not None else None
    workflows = tuple(item for item in all_workflows if selected is None or item.id in selected)
    schedules = tuple(sorted(store.list_schedules(workspace_id), key=lambda item: item.id.value))
    workflow_refs = {workflow.id: _ref("definition", workflow.to_json()) for workflow in workflows}
    objects: list[BundleInventoryObject] = []
    payloads: list[BundleFile] = []
    for workflow in workflows:
        logical_ref = workflow_refs[workflow.id]
        payload_path = _path("workflow", logical_ref)
        objects.append(BundleInventoryObject("workflow", logical_ref, payload_path))
        payloads.append(
            BundleFile(payload_path, WORKFLOW_MEDIA_TYPE, workflow.to_json().encode("utf-8"))
        )
    for schedule in schedules:
        workflow_ref = workflow_refs.get(schedule.workflow_id)
        if workflow_ref is None:
            raise ValueError("schedule references a workflow absent from the exported workspace")
        logical_ref = _ref("schedule", schedule.to_json())
        payload_path = _path("schedule", logical_ref)
        objects.append(
            BundleInventoryObject("schedule", logical_ref, payload_path, (workflow_ref,))
        )
        payloads.append(
            BundleFile(payload_path, SCHEDULE_MEDIA_TYPE, schedule.to_json().encode("utf-8"))
        )
    inventory = BundleInventory(tuple(objects))
    inventory_file = BundleFile(
        BUNDLE_INVENTORY_PATH, INVENTORY_MEDIA_TYPE, encode_canonical_json(inventory.to_payload())
    )
    return WorkflowBundleInventory(
        inventory, tuple(sorted((inventory_file, *payloads), key=lambda item: item.path))
    )


def export_workflow_bundle(
    store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    workflow_ids: tuple[object, ...] | Path,
    path: Path | None = None,
) -> RoninBundleManifest:
    if path is None:
        target = cast(Path, workflow_ids)
        selection = None
    else:
        target = path
        selection = cast(tuple[object, ...], workflow_ids)
    return write_bundle(
        target, build_workflow_bundle_inventory(store, workspace_id, selection).files
    )


def plan_workflow_bundle_import(
    path: Path,
    workspace_store: object | None = None,
    scheduler_store: SchedulerDefinitionStore | None = None,
    workspace_id: WorkspaceId | None = None,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 8 * 1024 * 1024,
) -> WorkflowBundleImportPlan:
    """Verify and parse a workflow Bundle without changing target state."""
    inventory_payload = read_bundle_payload(
        path, BUNDLE_INVENTORY_PATH, max_bytes=max_inventory_bytes, limits=limits
    )
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise BundleIntegrityError("workflow Bundle inventory has unsupported media type")
    try:
        inventory = BundleInventory.from_json(inventory_payload.file.data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleIntegrityError("workflow Bundle inventory is invalid") from exc
    objects: list[StagedWorkflowObject] = []
    known_refs = {item.logical_ref for item in inventory.objects}
    for item in inventory.objects:
        payload = read_bundle_payload(path, item.path, max_bytes=max_object_bytes, limits=limits)
        if payload.manifest != inventory_payload.manifest:
            raise BundleIntegrityError("workflow Bundle changed while import plan was constructed")
        try:
            if item.kind == "workflow":
                if item.dependencies or payload.file.media_type != WORKFLOW_MEDIA_TYPE:
                    raise ValueError("invalid workflow inventory entry")
                workflow_value = WorkflowDefinition.from_json(payload.file.data.decode("utf-8"))
                existing = (
                    scheduler_store.get_workflow(workspace_id, workflow_value.id)
                    if scheduler_store is not None and workspace_id is not None
                    else None
                )
                objects.append(
                    StagedWorkflowObject(
                        "workflow",
                        item.logical_ref,
                        workflow_value,
                        "noop"
                        if existing == workflow_value
                        else "collision"
                        if existing is not None
                        else "create",
                        "workflow definition conflicts"
                        if existing is not None and existing != workflow_value
                        else None,
                    )
                )
            elif item.kind == "schedule":
                if (
                    len(item.dependencies) != 1
                    or item.dependencies[0] not in known_refs
                    or payload.file.media_type != SCHEDULE_MEDIA_TYPE
                ):
                    raise ValueError("invalid schedule inventory entry")
                schedule_value = Schedule.from_json(payload.file.data.decode("utf-8"))
                existing_schedule = (
                    scheduler_store.get_schedule(workspace_id, schedule_value.id)
                    if scheduler_store is not None and workspace_id is not None
                    else None
                )
                objects.append(
                    StagedWorkflowObject(
                        "schedule",
                        item.logical_ref,
                        schedule_value,
                        "noop"
                        if existing_schedule == schedule_value
                        else "collision"
                        if existing_schedule is not None
                        else "create",
                        "schedule definition conflicts"
                        if existing_schedule is not None and existing_schedule != schedule_value
                        else None,
                    )
                )
            else:
                raise ValueError(f"unsupported workflow Bundle object kind: {item.kind}")
        except (UnicodeDecodeError, ValueError) as exc:
            raise BundleIntegrityError("workflow Bundle object is invalid") from exc
    workflows_sorted = tuple(
        cast(WorkflowDefinition, item.payload) for item in objects if item.kind == "workflow"
    )
    schedules_sorted = tuple(
        cast(Schedule, item.payload) for item in objects if item.kind == "schedule"
    )
    workflow_ids = {item.id for item in workflows_sorted}
    if len(workflow_ids) != len(workflows_sorted) or any(
        item.workflow_id not in workflow_ids for item in schedules_sorted
    ):
        raise BundleIntegrityError("workflow Bundle contains duplicate or unresolved definitions")
    return WorkflowBundleImportPlan(inventory_payload.manifest.digest, tuple(objects))


__all__ = (
    "INVENTORY_MEDIA_TYPE",
    "SCHEDULE_MEDIA_TYPE",
    "WORKFLOW_MEDIA_TYPE",
    "WorkflowBundleImportPlan",
    "WorkflowBundleInventory",
    "build_workflow_bundle_inventory",
    "export_workflow_bundle",
    "plan_workflow_bundle_import",
)
