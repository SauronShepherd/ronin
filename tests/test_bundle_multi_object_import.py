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
from studio_core.portability import BindingRequest
from studio_execution.bundle_connection import CONNECTION_BUNDLE_MEDIA_TYPE
from studio_execution.bundle_inventory import INVENTORY_MEDIA_TYPE, PROJECT_BUNDLE_MEDIA_TYPE
from studio_execution.bundle_multi_import import (
    UnsupportedMultiObjectBundle,
    plan_multi_object_bundle_import,
)
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.connections import SqliteConnectionStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T09:50:00.000000Z")
_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("project-1")
_CONNECTION = ConnectionId("warehouse-1")
_SECRET = SecretRef("secret://source/warehouse-password")


def _project(name: str = "Project") -> ProjectManifest:
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


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        _CONNECTION,
        "Warehouse",
        "postgresql",
        options=(("host", "db.example.test"),),
        secret_refs=(("password", _SECRET),),
    )


def _target(tmp_path: Path) -> tuple[SqliteWorkspaceStore, SqliteConnectionStore]:
    path = tmp_path / "target.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    return workspaces, SqliteConnectionStore(path, migration_now=_NOW)


def _write_project_connection_bundle(
    path: Path,
    *,
    cyclic: bool = False,
) -> None:
    connection_ref = f"connection:{_CONNECTION}"
    project_ref = f"project:{_PROJECT}"
    connection_path = "objects/connection/warehouse.json"
    project_path = "objects/project/project.json"
    connection_dependencies = (project_ref,) if cyclic else ()
    inventory = BundleInventory(
        (
            BundleInventoryObject(
                "connection",
                connection_ref,
                connection_path,
                dependencies=connection_dependencies,
                binding_requests=(BindingRequest("secret", str(_SECRET)),),
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


def test_multi_object_plan_orders_dependencies_and_does_not_mutate_target(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "multi.roninbundle"
    _write_project_connection_bundle(bundle)
    workspaces, connections = _target(tmp_path)

    plan = plan_multi_object_bundle_import(bundle, workspaces, connections, _WS)

    assert [item.logical_ref for item in plan.objects] == [
        f"connection:{_CONNECTION}",
        f"project:{_PROJECT}",
    ]
    assert [item.disposition for item in plan.objects] == ["create", "create"]
    assert not plan.has_collisions
    assert {(item.kind, item.source_ref) for item in plan.unresolved_bindings} == {
        ("secret", str(_SECRET)),
        ("runtime", "runtime-profile:python/3.11"),
    }
    assert workspaces.list_projects(_WS) == ()
    assert connections.list_connections(_WS) == ()


def test_multi_object_plan_reports_kind_specific_collisions(tmp_path: Path) -> None:
    bundle = tmp_path / "multi.roninbundle"
    _write_project_connection_bundle(bundle)
    workspaces, connections = _target(tmp_path)
    connections.create_connection(
        _WS,
        ConnectionDefinition(
            _CONNECTION,
            "Warehouse",
            "postgresql",
            options=(("host", "db.example.test"),),
            secret_refs=(("password", SecretRef("secret://target/password")),),
        ),
        now=_NOW,
    )
    workspaces.register_project(_WS, _project("Different project"), now=_NOW)

    plan = plan_multi_object_bundle_import(bundle, workspaces, connections, _WS)

    assert plan.has_collisions
    assert [item.disposition for item in plan.objects] == ["existing", "collision"]
    assert plan.objects[1].collision_reason is not None


def test_multi_object_plan_rejects_cyclic_dependencies(tmp_path: Path) -> None:
    bundle = tmp_path / "cycle.roninbundle"
    _write_project_connection_bundle(bundle, cyclic=True)
    workspaces, connections = _target(tmp_path)

    with pytest.raises(UnsupportedMultiObjectBundle, match="cyclic"):
        plan_multi_object_bundle_import(bundle, workspaces, connections, _WS)
    assert workspaces.list_projects(_WS) == ()
    assert connections.list_connections(_WS) == ()


def test_multi_object_plan_rejects_unknown_object_kind(tmp_path: Path) -> None:
    object_path = "objects/future/object.json"
    inventory = BundleInventory(
        (BundleInventoryObject("future", "future:1", object_path),)
    )
    bundle = tmp_path / "future.roninbundle"
    write_bundle(
        bundle,
        (
            BundleFile(
                BUNDLE_INVENTORY_PATH,
                INVENTORY_MEDIA_TYPE,
                inventory.to_json().encode("utf-8"),
            ),
            BundleFile(object_path, "application/json", b"{}"),
        ),
    )
    workspaces, connections = _target(tmp_path)

    with pytest.raises(UnsupportedMultiObjectBundle, match="unsupported native Bundle object kind"):
        plan_multi_object_bundle_import(bundle, workspaces, connections, _WS)
    assert workspaces.list_projects(_WS) == ()
    assert connections.list_connections(_WS) == ()
