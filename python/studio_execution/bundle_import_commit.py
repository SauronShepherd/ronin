"""Binding resolution and atomic commit for native Ronin project bundles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio_core import WorkspaceId
from studio_core.environments import (
    DeploymentBinding,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_orchestrator import Instant
from studio_storage.bundle import BundleReadLimits
from studio_storage.bundle_import_port import (
    ProjectBundleImportCommit,
    ProjectBundleImportConflict,
    ProjectBundleImportStore,
)

from .bundle_import import ProjectBundleImportPlan, plan_project_bundle_import


class BundleBindingResolutionError(ValueError):
    """Raised when deployment binding resolutions do not match Bundle requests."""


@dataclass(frozen=True, slots=True)
class ProjectBundleImportOutcome:
    plan: ProjectBundleImportPlan
    bindings: ProjectEnvironmentBindings | None
    commit: ProjectBundleImportCommit


def resolve_project_import_bindings(
    plan: ProjectBundleImportPlan,
    environment_id: EnvironmentId | None,
    resolutions: tuple[DeploymentBinding, ...],
) -> ProjectEnvironmentBindings | None:
    """Validate explicit deployment remaps against the Bundle's binding requests."""

    expected = {(request.kind, request.source_ref): request for request in plan.unresolved_bindings}
    supplied: dict[tuple[str, str], DeploymentBinding] = {}
    for resolution in resolutions:
        key = (resolution.kind, resolution.source_ref)
        if key in supplied:
            raise BundleBindingResolutionError("duplicate Bundle binding resolution")
        if key not in expected:
            raise BundleBindingResolutionError("Bundle binding resolution was not requested")
        supplied[key] = resolution

    missing_required = [
        request
        for key, request in expected.items()
        if request.required and key not in supplied
    ]
    if missing_required:
        raise BundleBindingResolutionError("required Bundle bindings remain unresolved")
    if not supplied:
        return None
    if environment_id is None:
        raise BundleBindingResolutionError(
            "target environment is required when Bundle bindings are resolved"
        )
    return ProjectEnvironmentBindings(
        plan.project_id,
        environment_id,
        tuple(supplied.values()),
    )


def commit_project_bundle_import(
    bundle_path: Path,
    store: ProjectBundleImportStore,
    workspace_id: WorkspaceId,
    *,
    environment_id: EnvironmentId | None = None,
    resolutions: tuple[DeploymentBinding, ...] = (),
    now: Instant | str,
    limits: BundleReadLimits = BundleReadLimits(),
    max_inventory_bytes: int = 8 * 1024 * 1024,
    max_project_bytes: int = 8 * 1024 * 1024,
) -> ProjectBundleImportOutcome:
    """Re-plan from verified bytes, resolve bindings, then atomically commit target state."""

    plan = plan_project_bundle_import(
        bundle_path,
        store,
        workspace_id,
        limits=limits,
        max_inventory_bytes=max_inventory_bytes,
        max_project_bytes=max_project_bytes,
    )
    if plan.disposition == "collision":
        raise ProjectBundleImportConflict(plan.collision_reason or "project import collision")
    bindings = resolve_project_import_bindings(plan, environment_id, resolutions)
    commit = store.commit_project_import(
        workspace_id,
        plan.project,
        bindings,
        now=now,
    )
    return ProjectBundleImportOutcome(plan, bindings, commit)


__all__ = (
    "BundleBindingResolutionError",
    "ProjectBundleImportOutcome",
    "commit_project_bundle_import",
    "resolve_project_import_bindings",
)
