from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import (
    ConnectionDefinition,
    ConnectionId,
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    SecretRef,
    Workspace,
    WorkspaceId,
)
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.environments import DeploymentBinding, EnvironmentDefinition, EnvironmentId
from studio_core.portability import BindingRequest
from studio_execution.bundle_connection import CONNECTION_BUNDLE_MEDIA_TYPE
from studio_execution.bundle_inventory import INVENTORY_MEDIA_TYPE, PROJECT_BUNDLE_MEDIA_TYPE
from studio_execution.bundle_multi_commit import (
    MultiObjectBundleBindingError,
    ProjectTargetEnvironment,
    commit_multi_object_bundle_import,
)
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_multi_import import SqliteMultiObjectBundleImportStore
from studio_storage.bundle_multi_import_port import MultiObjectBundleImportConflict
from studio_storage.environments import SqliteEnvironmentStore

_NOW = Instant("2026-09-13T10:00:00.000000Z")
_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("project-1")
_CONNECTION = ConnectionId("warehouse-1")
_ENV = EnvironmentId("local")
_SOURCE_SECRET = SecretRef("secret://source/warehouse-password")
_TARGET_SECRET = SecretRef("secret://target/warehouse-password")


def _project() -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            _PROJECT,
            "Project",
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


def _connection(secret_ref: SecretRef = _SOURCE_SECRET) -> ConnectionDefinition:
    return ConnectionDefinition(
        _CONNECTION,
        "Warehouse",
        "postgresql",
        options=(("host", "db.example.test"),),
        secret_refs=(("password", secret_ref),),
    )


def _write_bundle(path: Path) -> None:
    connection_ref = f"connection:{_CONNECTION}"
    project_ref = f"project:{_PROJECT}"
    connection_path = "objects/connection/warehouse.json"
    project_path = "objects/project/project.json"
    inventory = BundleInventory(
        (
            BundleInventoryObject(
                "connection",
                connection_ref,
                connection_path,
                binding_requests=(BindingRequest("secret", str(_SOURCE_SECRET)),),
            ),
            BundleInventoryObject(
                "project",
                project_ref,
                project_path,
                dependencies=(connection_ref,),
                binding_requests=(
                    BindingRequest("runtime", "runtime-profile:python/3.11"),
                ),
            ),
        )
    )
    write_bundle(
        path,
        (
            BundleFile(
                BUNDLE_INVENTORY_PATH,
                INVENTORY_MEDIA_TYPE,
                inventory.to_json().encode("utf-8"),
            ),
            BundleFile(
                connection_path,
                CONNECTION_BUNDLE_MEDIA_TYPE,
                _connection().to_json().encode("utf-8"),
            ),
            BundleFile(
                project_path,
                PROJECT_BUNDLE_MEDIA_TYPE,
                _project().to_json().encode("utf-8"),
            ),
        ),
    )


def _target(
    tmp_path: Path,
    *,
    with_environment: bool = True,
) -> tuple[SqliteMultiObjectBundleImportStore, SqliteEnvironmentStore]:
    path = tmp_path / "target.sqlite3"
    store = SqliteMultiObjectBundleImportStore(path, migration_now=_NOW)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    environments = SqliteEnvironmentStore(path, migration_now=_NOW)
    if with_environment:
        environments.put_environment(
            _WS,
            EnvironmentDefinition(_ENV, "Local"),
            now=_NOW,
        )
    return store, environments


def _resolutions() -> tuple[DeploymentBinding, ...]:
    return (
        DeploymentBinding("secret", str(_SOURCE_SECRET), str(_TARGET_SECRET)),
        DeploymentBinding(
            "runtime",
            "runtime-profile:python/3.11",
            "runtime://python311",
        ),
    )


def _project_target() -> tuple[ProjectTargetEnvironment, ...]:
    return (ProjectTargetEnvironment(f"project:{_PROJECT}", _ENV),)


def test_multi_object_commit_is_atomic_and_retry_safe(tmp_path: Path) -> None:
    bundle = tmp_path / "multi.roninbundle"
    _write_bundle(bundle)
    store, environments = _target(tmp_path)

    first = commit_multi_object_bundle_import(
        bundle,
        store,
        _WS,
        resolutions=_resolutions(),
        project_environments=_project_target(),
        now=_NOW,
    )
    assert first.commit.connections_created == 1
    assert first.commit.projects_created == 1
    assert first.commit.bindings_created == 1
    assert store.get_connection(_WS, _CONNECTION) == _connection(_TARGET_SECRET)
    assert store.get_project(_WS, _PROJECT) == _project()
    bindings = environments.get_project_bindings(_WS, _PROJECT, _ENV)
    assert bindings is not None
    assert {(item.kind, item.target_ref) for item in bindings.bindings} == {
        ("runtime", "runtime://python311")
    }

    second = commit_multi_object_bundle_import(
        bundle,
        store,
        _WS,
        resolutions=_resolutions(),
        project_environments=_project_target(),
        now=_NOW,
    )
    assert second.commit.connections_created == 0
    assert second.commit.projects_created == 0
    assert second.commit.bindings_created == 0


def test_multi_object_commit_rejects_unresolved_bindings_before_mutation(tmp_path: Path) -> None:
    bundle = tmp_path / "multi.roninbundle"
    _write_bundle(bundle)
    store, _environments = _target(tmp_path)

    with pytest.raises(MultiObjectBundleBindingError, match="remain unresolved"):
        commit_multi_object_bundle_import(
            bundle,
            store,
            _WS,
            resolutions=(_resolutions()[0],),
            project_environments=_project_target(),
            now=_NOW,
        )
    assert store.list_connections(_WS) == ()
    assert store.list_projects(_WS) == ()


def test_multi_object_commit_rolls_back_all_objects_when_environment_is_missing(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "multi.roninbundle"
    _write_bundle(bundle)
    store, _environments = _target(tmp_path, with_environment=False)

    with pytest.raises(MultiObjectBundleImportConflict, match="environment does not exist"):
        commit_multi_object_bundle_import(
            bundle,
            store,
            _WS,
            resolutions=_resolutions(),
            project_environments=_project_target(),
            now=_NOW,
        )
    assert store.list_connections(_WS) == ()
    assert store.list_projects(_WS) == ()


def test_multi_object_commit_rolls_back_project_when_resolved_connection_conflicts(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "multi.roninbundle"
    _write_bundle(bundle)
    store, _environments = _target(tmp_path)
    existing = _connection(SecretRef("secret://target/existing-password"))
    store.create_connection(_WS, existing, now=_NOW)

    with pytest.raises(MultiObjectBundleImportConflict, match="connection id already exists"):
        commit_multi_object_bundle_import(
            bundle,
            store,
            _WS,
            resolutions=_resolutions(),
            project_environments=_project_target(),
            now=_NOW,
        )
    assert store.get_connection(_WS, _CONNECTION) == existing
    assert store.list_projects(_WS) == ()
