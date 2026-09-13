"""Explicit binding resolution and atomic commit for supported multi-object Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio_core import ConnectionDefinition, ProjectManifest, SecretRef, WorkspaceId
from studio_core.environments import (
    DeploymentBinding,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_orchestrator import Instant
from studio_storage.bundle import BundleReadLimits
from studio_storage.bundle_multi_import_port import (
    MultiObjectBundleImportCommit,
    MultiObjectBundleImportConflict,
    MultiObjectBundleImportStore,
)

from .bundle_multi_import import (
    MultiObjectBundleImportPlan,
    StagedBundleObject,
    plan_multi_object_bundle_import,
)


class MultiObjectBundleBindingError(ValueError):
    """Raised when explicit deployment remaps do not exactly satisfy staged requests."""


@dataclass(frozen=True, order=True, slots=True)
class ProjectTargetEnvironment:
    logical_ref: str
    environment_id: EnvironmentId

    def __post_init__(self) -> None:
        if not self.logical_ref or self.logical_ref != self.logical_ref.strip():
            raise ValueError("project target logical_ref must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class MultiObjectBundleImportOutcome:
    plan: MultiObjectBundleImportPlan
    resolved_connections: tuple[ConnectionDefinition, ...]
    project_bindings: tuple[ProjectEnvironmentBindings, ...]
    commit: MultiObjectBundleImportCommit


def _resolution_map(
    plan: MultiObjectBundleImportPlan,
    resolutions: tuple[DeploymentBinding, ...],
) -> dict[tuple[str, str], DeploymentBinding]:
    expected = {(item.kind, item.source_ref): item for item in plan.unresolved_bindings}
    supplied: dict[tuple[str, str], DeploymentBinding] = {}
    for resolution in resolutions:
        key = (resolution.kind, resolution.source_ref)
        if key in supplied:
            raise MultiObjectBundleBindingError("duplicate multi-object Bundle binding resolution")
        if key not in expected:
            raise MultiObjectBundleBindingError(
                "multi-object Bundle binding resolution was not requested"
            )
        supplied[key] = resolution
    if any(request.required and key not in supplied for key, request in expected.items()):
        raise MultiObjectBundleBindingError(
            "required multi-object Bundle bindings remain unresolved"
        )
    return supplied


def _environment_map(
    plan: MultiObjectBundleImportPlan,
    targets: tuple[ProjectTargetEnvironment, ...],
) -> dict[str, EnvironmentId]:
    project_refs = {
        item.logical_ref
        for item in plan.objects
        if item.kind == "project" and item.unresolved_bindings
    }
    supplied: dict[str, EnvironmentId] = {}
    for target in targets:
        if target.logical_ref in supplied:
            raise MultiObjectBundleBindingError("duplicate project target environment")
        if target.logical_ref not in project_refs:
            raise MultiObjectBundleBindingError(
                "project target environment was not requested by staged bindings"
            )
        supplied[target.logical_ref] = target.environment_id
    if set(supplied) != project_refs:
        raise MultiObjectBundleBindingError(
            "project target environment is required for every bound staged project"
        )
    return supplied


def _resolve_connection(
    item: StagedBundleObject,
    resolutions: dict[tuple[str, str], DeploymentBinding],
) -> ConnectionDefinition:
    if not isinstance(item.payload, ConnectionDefinition):
        raise TypeError("staged connection payload has unexpected type")
    remapped: list[tuple[str, SecretRef]] = []
    for key, source_ref in item.payload.secret_refs:
        resolution = resolutions.get(("secret", str(source_ref)))
        if resolution is None:
            remapped.append((key, source_ref))
        else:
            remapped.append((key, SecretRef(resolution.target_ref)))
    return ConnectionDefinition(
        item.payload.id,
        item.payload.name,
        item.payload.connector_id,
        item.payload.options,
        tuple(remapped),
    )


def _resolve_project_bindings(
    item: StagedBundleObject,
    resolutions: dict[tuple[str, str], DeploymentBinding],
    environments: dict[str, EnvironmentId],
) -> ProjectEnvironmentBindings | None:
    if not isinstance(item.payload, ProjectManifest):
        raise TypeError("staged project payload has unexpected type")
    if not item.unresolved_bindings:
        return None
    environment_id = environments[item.logical_ref]
    resolved: list[DeploymentBinding] = []
    for request in item.unresolved_bindings:
        binding = resolutions.get((request.kind, request.source_ref))
        if binding is None:
            if request.required:
                raise MultiObjectBundleBindingError(
                    "required staged project binding remains unresolved"
                )
            continue
        resolved.append(binding)
    return ProjectEnvironmentBindings(
        item.payload.project.id,
        environment_id,
        tuple(resolved),
    )


def commit_multi_object_bundle_import(
    bundle_path: Path,
    store: MultiObjectBundleImportStore,
    workspace_id: WorkspaceId,
    *,
    resolutions: tuple[DeploymentBinding, ...] = (),
    project_environments: tuple[ProjectTargetEnvironment, ...] = (),
    now: Instant | str,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_object_bytes: int = 8 * 1024 * 1024,
) -> MultiObjectBundleImportOutcome:
    """Re-plan verified bytes, resolve all bindings, then commit every object atomically."""

    plan = plan_multi_object_bundle_import(
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
        raise MultiObjectBundleImportConflict(
            collisions[0].collision_reason or "multi-object Bundle import collision"
        )

    resolution_map = _resolution_map(plan, resolutions)
    environment_map = _environment_map(plan, project_environments)
    connections: list[ConnectionDefinition] = []
    projects: list[ProjectManifest] = []
    bindings: list[ProjectEnvironmentBindings] = []
    for item in plan.objects:
        if item.kind == "connection":
            connections.append(_resolve_connection(item, resolution_map))
        elif item.kind == "project":
            if not isinstance(item.payload, ProjectManifest):
                raise TypeError("staged project payload has unexpected type")
            projects.append(item.payload)
            project_bindings = _resolve_project_bindings(
                item,
                resolution_map,
                environment_map,
            )
            if project_bindings is not None:
                bindings.append(project_bindings)
        else:
            raise AssertionError(f"unsupported staged object kind: {item.kind}")

    commit = store.commit_multi_object_import(
        workspace_id,
        tuple(connections),
        tuple(projects),
        tuple(bindings),
        now=now,
    )
    return MultiObjectBundleImportOutcome(
        plan,
        tuple(connections),
        tuple(bindings),
        commit,
    )


__all__ = (
    "MultiObjectBundleBindingError",
    "MultiObjectBundleImportOutcome",
    "ProjectTargetEnvironment",
    "commit_multi_object_bundle_import",
)
