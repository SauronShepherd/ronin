"""Native Ronin Bundle export/planning for portable workflow and schedule intent."""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from studio_core import Schedule, ScheduleId, WorkflowDefinition, WorkflowId, WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import (
    BundleFile,
    BundleIntegrityError,
    BundleReadLimits,
    write_bundle,
)
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.bundle_workflow_import_port import SchedulerDefinitionStore
from studio_storage.ports import WorkspaceStore

WORKFLOW_MEDIA_TYPE = "application/vnd.ronin.workflow+json"
SCHEDULE_MEDIA_TYPE = "application/vnd.ronin.schedule+json"
INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"

WorkflowDisposition: TypeAlias = Literal["create", "noop", "collision"]
WorkflowPayload: TypeAlias = WorkflowDefinition | Schedule


class UnsupportedWorkflowBundle(ValueError):
    """Raised when workflow Bundle semantics cannot be interpreted without loss."""


class WorkflowBundleTargetError(ValueError):
    """Raised when the target workspace cannot accept workflow import planning."""


@dataclass(frozen=True, slots=True)
class WorkflowBundleInventory:
    inventory: BundleInventory
    files: tuple[BundleFile, ...]

    def __post_init__(self) -> None:
        paths = tuple(file.path for file in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("workflow Bundle file paths must be unique")
        expected = {BUNDLE_INVENTORY_PATH, *(item.path for item in self.inventory.objects)}
        if set(paths) != expected:
            raise ValueError(
                "workflow Bundle files must exactly match semantic inventory paths"
            )


@dataclass(frozen=True, slots=True)
class StagedWorkflowObject:
    kind: str
    logical_ref: str
    dependencies: tuple[str, ...]
    payload_digest: str
    payload: WorkflowPayload
    disposition: WorkflowDisposition
    collision_reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition == "collision":
            if self.collision_reason is None:
                raise ValueError("workflow collision requires a reason")
        elif self.collision_reason is not None:
            raise ValueError("non-collision workflow object cannot include a reason")


@dataclass(frozen=True, slots=True)
class WorkflowBundleImportPlan:
    bundle_manifest_digest: str
    inventory_digest: str
    objects: tuple[StagedWorkflowObject, ...]

    @property
    def has_collisions(self) -> bool:
        return any(item.disposition == "collision" for item in self.objects)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _workflow_logical_ref(workflow_id: WorkflowId) -> str:
    return f"workflow:{workflow_id}"


def _schedule_logical_ref(schedule_id: ScheduleId) -> str:
    return f"schedule:{schedule_id}"


def _payload_path(kind: str, logical_ref: str) -> str:
    return f"objects/workflow/{kind}/{_hash_text(logical_ref)}.json"


def _manifest_entry_digest(manifest: RoninBundleManifest, path: str) -> str:
    for entry in manifest.entries:
        if entry.path == path:
            return entry.digest
    raise BundleIntegrityError(
        "workflow inventory references a payload absent from manifest"
    )


def _require_active_workspace(store: WorkspaceStore, workspace_id: WorkspaceId) -> None:
    workspace = store.get_workspace(workspace_id)
    if workspace is None:
        raise WorkflowBundleTargetError("target workspace does not exist")
    if workspace.archived:
        raise WorkflowBundleTargetError("target workspace is archived")


def build_workflow_bundle_inventory(
    store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    workflow_ids: tuple[WorkflowId, ...],
) -> WorkflowBundleInventory:
    """Build portable workflow definitions and their schedules, never runtime state."""

    selected_ids = tuple(sorted(workflow_ids))
    if not selected_ids:
        raise ValueError("workflow Bundle selection must include at least one workflow")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("workflow Bundle selected workflows must be unique")

    workflows: list[WorkflowDefinition] = []
    for workflow_id in selected_ids:
        workflow = store.get_workflow(workspace_id, workflow_id)
        if workflow is None:
            raise KeyError(str(workflow_id))
        workflows.append(workflow)

    selected = set(selected_ids)
    schedules = tuple(
        schedule
        for schedule in store.list_schedules(workspace_id)
        if schedule.workflow_id in selected
    )
    workflow_refs = {
        workflow.id: _workflow_logical_ref(workflow.id) for workflow in workflows
    }
    objects: list[BundleInventoryObject] = []
    payloads: list[BundleFile] = []

    for workflow in sorted(workflows, key=lambda item: item.id.value):
        logical_ref = workflow_refs[workflow.id]
        path = _payload_path("definition", logical_ref)
        objects.append(BundleInventoryObject("workflow", logical_ref, path))
        payloads.append(
            BundleFile(
                path,
                WORKFLOW_MEDIA_TYPE,
                workflow.to_json().encode("utf-8"),
            )
        )

    for schedule in sorted(schedules, key=lambda item: item.id.value):
        workflow_ref = workflow_refs.get(schedule.workflow_id)
        if workflow_ref is None:
            raise AssertionError("selected schedule references an unselected workflow")
        logical_ref = _schedule_logical_ref(schedule.id)
        path = _payload_path("schedule", logical_ref)
        objects.append(
            BundleInventoryObject(
                "schedule",
                logical_ref,
                path,
                dependencies=(workflow_ref,),
            )
        )
        payloads.append(
            BundleFile(
                path,
                SCHEDULE_MEDIA_TYPE,
                schedule.to_json().encode("utf-8"),
            )
        )

    inventory = BundleInventory(tuple(objects))
    files = (
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            inventory.to_json().encode("utf-8"),
        ),
        *payloads,
    )
    return WorkflowBundleInventory(
        inventory,
        tuple(sorted(files, key=lambda item: item.path)),
    )


def export_workflow_bundle(
    store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    workflow_ids: tuple[WorkflowId, ...],
    path: Path,
) -> RoninBundleManifest:
    """Write deterministic portable workflow/schedule definitions."""

    built = build_workflow_bundle_inventory(store, workspace_id, workflow_ids)
    return write_bundle(path, built.files)


def _ordered_objects(inventory: BundleInventory) -> tuple[BundleInventoryObject, ...]:
    by_ref = {item.logical_ref: item for item in inventory.objects}
    indegree = {item.logical_ref: len(item.dependencies) for item in inventory.objects}
    dependents: dict[str, list[str]] = {ref: [] for ref in by_ref}
    for item in inventory.objects:
        for dependency in item.dependencies:
            dependents[dependency].append(item.logical_ref)
    ready = [ref for ref, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[BundleInventoryObject] = []
    while ready:
        logical_ref = heapq.heappop(ready)
        ordered.append(by_ref[logical_ref])
        for dependent in sorted(dependents[logical_ref]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)
    if len(ordered) != len(inventory.objects):
        raise UnsupportedWorkflowBundle("workflow Bundle dependency graph is cyclic")
    return tuple(ordered)


def _stage_workflow(
    item: BundleInventoryObject,
    data: bytes,
    store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    digest: str,
) -> StagedWorkflowObject:
    if item.dependencies or item.binding_requests:
        raise UnsupportedWorkflowBundle(
            "workflow definition must not depend on deployment/runtime Bundle state"
        )
    try:
        workflow = WorkflowDefinition.from_json(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedWorkflowBundle("workflow definition payload is invalid") from exc
    if item.logical_ref != _workflow_logical_ref(workflow.id):
        raise UnsupportedWorkflowBundle(
            "workflow logical identity does not match definition payload"
        )
    existing = store.get_workflow(workspace_id, workflow.id)
    if existing is None:
        disposition: WorkflowDisposition = "create"
        reason = None
    elif existing == workflow:
        disposition = "noop"
        reason = None
    else:
        disposition = "collision"
        reason = "workflow id already exists with different portable definition"
    return StagedWorkflowObject(
        "workflow",
        item.logical_ref,
        item.dependencies,
        digest,
        workflow,
        disposition,
        reason,
    )


def _stage_schedule(
    item: BundleInventoryObject,
    data: bytes,
    store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    digest: str,
    known_workflows: dict[WorkflowId, str],
) -> StagedWorkflowObject:
    if item.binding_requests:
        raise UnsupportedWorkflowBundle(
            "schedule must not request deployment/runtime bindings"
        )
    try:
        schedule = Schedule.from_json(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedWorkflowBundle("schedule payload is invalid") from exc
    expected_dependency = known_workflows.get(schedule.workflow_id)
    if expected_dependency is None or item.dependencies != (expected_dependency,):
        raise UnsupportedWorkflowBundle(
            "schedule dependency does not match workflow payload"
        )
    if item.logical_ref != _schedule_logical_ref(schedule.id):
        raise UnsupportedWorkflowBundle(
            "schedule logical identity does not match payload"
        )
    existing = store.get_schedule(workspace_id, schedule.id)
    if existing is None:
        disposition: WorkflowDisposition = "create"
        reason = None
    elif existing == schedule:
        disposition = "noop"
        reason = None
    else:
        disposition = "collision"
        reason = "schedule id already exists with different portable definition"
    return StagedWorkflowObject(
        "schedule",
        item.logical_ref,
        item.dependencies,
        digest,
        schedule,
        disposition,
        reason,
    )


def plan_workflow_bundle_import(
    bundle_path: Path,
    workspace_store: WorkspaceStore,
    scheduler_store: SchedulerDefinitionStore,
    workspace_id: WorkspaceId,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 16 * 1024 * 1024,
) -> WorkflowBundleImportPlan:
    """Verify and classify portable workflow/schedule definitions without mutation."""

    _require_active_workspace(workspace_store, workspace_id)
    inventory_payload = read_bundle_payload(
        bundle_path,
        BUNDLE_INVENTORY_PATH,
        max_bytes=max_inventory_bytes,
        limits=limits,
    )
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise UnsupportedWorkflowBundle(
            "workflow Bundle inventory has unsupported media type"
        )
    try:
        inventory = BundleInventory.from_json(
            inventory_payload.file.data.decode("utf-8")
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise UnsupportedWorkflowBundle("workflow Bundle inventory is invalid") from exc

    staged: list[StagedWorkflowObject] = []
    known_workflows: dict[WorkflowId, str] = {}
    for item in _ordered_objects(inventory):
        payload = read_bundle_payload(
            bundle_path,
            item.path,
            max_bytes=max_object_bytes,
            limits=limits,
        )
        if payload.manifest != inventory_payload.manifest:
            raise BundleIntegrityError(
                "workflow Bundle changed while import plan was constructed"
            )
        digest = _manifest_entry_digest(inventory_payload.manifest, item.path)
        if item.kind == "workflow":
            if payload.file.media_type != WORKFLOW_MEDIA_TYPE:
                raise UnsupportedWorkflowBundle(
                    "workflow definition has unsupported media type"
                )
            staged_item = _stage_workflow(
                item,
                payload.file.data,
                scheduler_store,
                workspace_id,
                digest,
            )
            assert isinstance(staged_item.payload, WorkflowDefinition)
            known_workflows[staged_item.payload.id] = staged_item.logical_ref
        elif item.kind == "schedule":
            if payload.file.media_type != SCHEDULE_MEDIA_TYPE:
                raise UnsupportedWorkflowBundle(
                    "schedule has unsupported media type"
                )
            staged_item = _stage_schedule(
                item,
                payload.file.data,
                scheduler_store,
                workspace_id,
                digest,
                known_workflows,
            )
        else:
            raise UnsupportedWorkflowBundle(
                f"unsupported workflow Bundle object kind: {item.kind}"
            )
        staged.append(staged_item)

    return WorkflowBundleImportPlan(
        inventory_payload.manifest.digest,
        inventory.digest,
        tuple(staged),
    )


__all__ = (
    "INVENTORY_MEDIA_TYPE",
    "SCHEDULE_MEDIA_TYPE",
    "WORKFLOW_MEDIA_TYPE",
    "StagedWorkflowObject",
    "UnsupportedWorkflowBundle",
    "WorkflowBundleImportPlan",
    "WorkflowBundleInventory",
    "WorkflowBundleTargetError",
    "build_workflow_bundle_inventory",
    "export_workflow_bundle",
    "plan_workflow_bundle_import",
)
