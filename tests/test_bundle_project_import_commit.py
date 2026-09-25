from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import (
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    Workspace,
    WorkspaceId,
)
from studio_core.environments import DeploymentBinding, EnvironmentDefinition, EnvironmentId
from studio_execution.bundle_import import plan_project_bundle_import
from studio_execution.bundle_import_commit import (
    BundleBindingResolutionError,
    commit_project_bundle_import,
)
from studio_execution.bundle_inventory import export_project_bundle
from studio_orchestrator import Instant
from studio_storage.bundle_import import SqliteProjectBundleImportStore
from studio_storage.bundle_import_port import ProjectBundleImportConflict
from studio_storage.environments import SqliteEnvironmentStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T09:30:00.000000Z")
_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("project-1")
_ENV = EnvironmentId("local")


def _manifest(name: str = "Portable project") -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            _PROJECT,
            name,
            (
                RepositoryBinding(
                    "code",
                    "https://git.example.test/team/repo.git",
                    role="primary",
                ),
            ),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _export(tmp_path: Path) -> Path:
    source_path = tmp_path / "source.sqlite3"
    source = SqliteWorkspaceStore(source_path, migration_now=_NOW)
    source.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    source.register_project(_WS, _manifest(), now=_NOW)
    bundle = tmp_path / "project.roninbundle"
    export_project_bundle(source, _WS, _PROJECT, bundle)
    return bundle


def _target(tmp_path: Path, *, with_environment: bool = True):
    path = tmp_path / "target.sqlite3"
    store = SqliteProjectBundleImportStore(path, migration_now=_NOW)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    environments = SqliteEnvironmentStore(path, migration_now=_NOW)
    if with_environment:
        environments.put_environment(
            _WS,
            EnvironmentDefinition(_ENV, "Local"),
            now=_NOW,
        )
    return store, environments


def _runtime_resolution(target: str = "runtime://python311") -> DeploymentBinding:
    return DeploymentBinding(
        "runtime",
        "runtime-profile:python/3.11",
        target,
    )


def test_project_bundle_commit_resolves_runtime_and_is_retry_safe(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    store, environments = _target(tmp_path)

    first = commit_project_bundle_import(
        bundle,
        store,
        _WS,
        environment_id=_ENV,
        resolutions=(_runtime_resolution(),),
        now=_NOW,
    )
    assert first.plan.disposition == "create"
    assert first.commit.project_created
    assert first.commit.bindings_created
    assert store.get_project(_WS, _PROJECT) == _manifest()
    bindings = environments.get_project_bindings(_WS, _PROJECT, _ENV)
    assert bindings is not None
    assert bindings.bindings == (_runtime_resolution(),)

    second = commit_project_bundle_import(
        bundle,
        store,
        _WS,
        environment_id=_ENV,
        resolutions=(_runtime_resolution(),),
        now=_NOW,
    )
    assert second.plan.disposition == "noop"
    assert not second.commit.project_created
    assert not second.commit.bindings_created


def test_project_bundle_commit_requires_exact_requested_bindings(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    store, _environments = _target(tmp_path)

    with pytest.raises(BundleBindingResolutionError, match="remain unresolved"):
        commit_project_bundle_import(bundle, store, _WS, now=_NOW)
    assert store.get_project(_WS, _PROJECT) is None

    unknown = DeploymentBinding("runtime", "runtime-profile:other/1", "runtime://other")
    with pytest.raises(BundleBindingResolutionError, match="was not requested"):
        commit_project_bundle_import(
            bundle,
            store,
            _WS,
            environment_id=_ENV,
            resolutions=(unknown,),
            now=_NOW,
        )
    assert store.get_project(_WS, _PROJECT) is None


def test_project_bundle_commit_rolls_back_project_when_environment_is_missing(
    tmp_path: Path,
) -> None:
    bundle = _export(tmp_path)
    store, _environments = _target(tmp_path, with_environment=False)

    with pytest.raises(ProjectBundleImportConflict, match="environment does not exist"):
        commit_project_bundle_import(
            bundle,
            store,
            _WS,
            environment_id=_ENV,
            resolutions=(_runtime_resolution(),),
            now=_NOW,
        )
    assert store.get_project(_WS, _PROJECT) is None


def test_atomic_commit_rechecks_project_after_read_only_plan(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    store, _environments = _target(tmp_path)
    plan = plan_project_bundle_import(bundle, store, _WS)
    assert plan.disposition == "create"

    store.register_project(_WS, _manifest("Concurrent target content"), now=_NOW)

    with pytest.raises(ProjectBundleImportConflict, match="different portable content"):
        store.commit_project_import(_WS, plan.project, None, now=_NOW)
    assert store.get_project(_WS, _PROJECT) == _manifest("Concurrent target content")
