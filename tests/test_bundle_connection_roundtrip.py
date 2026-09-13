from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import ConnectionDefinition, ConnectionId, SecretRef, Workspace, WorkspaceId
from studio_core.environments import DeploymentBinding
from studio_execution.bundle_connection import (
    ConnectionBundleBindingError,
    ConnectionBundleImportConflict,
    build_connection_bundle_inventory,
    commit_connection_bundle_import,
    export_connection_bundle,
    plan_connection_bundle_import,
)
from studio_orchestrator import Instant
from studio_storage.bundle import verify_bundle
from studio_storage.connections import ConnectionConflict, SqliteConnectionStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T09:40:00.000000Z")
_WS = WorkspaceId("workspace-1")
_CONNECTION = ConnectionId("warehouse/primary with spaces")
_SOURCE_SECRET = SecretRef("secret://source/warehouse-password")
_TARGET_SECRET = SecretRef("secret://target/warehouse-password")


def _definition(
    *,
    name: str = "Warehouse",
    secret_ref: SecretRef = _SOURCE_SECRET,
) -> ConnectionDefinition:
    return ConnectionDefinition(
        id=_CONNECTION,
        name=name,
        connector_id="postgresql",
        options=(("host", "db.example.test"), ("database", "analytics")),
        secret_refs=(("password", secret_ref),),
    )


def _stores(path: Path) -> tuple[SqliteWorkspaceStore, SqliteConnectionStore]:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    return workspaces, SqliteConnectionStore(path, migration_now=_NOW)


def _export(tmp_path: Path) -> Path:
    workspaces, connections = _stores(tmp_path / "source.sqlite3")
    assert workspaces.get_workspace(_WS) is not None
    connections.create_connection(_WS, _definition(), now=_NOW)
    bundle = tmp_path / "connection.roninbundle"
    export_connection_bundle(connections, _WS, _CONNECTION, bundle)
    return bundle


def _resolution(target: SecretRef = _TARGET_SECRET) -> DeploymentBinding:
    return DeploymentBinding("secret", str(_SOURCE_SECRET), str(target))


def test_connection_bundle_export_is_deterministic_and_requests_secret_remap(
    tmp_path: Path,
) -> None:
    workspaces, connections = _stores(tmp_path / "source.sqlite3")
    assert workspaces.get_workspace(_WS) is not None
    connections.create_connection(_WS, _definition(), now=_NOW)

    built = build_connection_bundle_inventory(connections, _WS, _CONNECTION)
    assert len(built.inventory.objects) == 1
    item = built.inventory.objects[0]
    assert item.kind == "connection"
    assert item.logical_ref == f"connection:{_CONNECTION}"
    assert item.path.startswith("objects/connection/")
    assert str(_CONNECTION) not in item.path
    assert built.inventory.unresolved_bindings == (
        built.inventory.objects[0].binding_requests[0],
    )
    request = built.inventory.unresolved_bindings[0]
    assert request.kind == "secret"
    assert request.source_ref == str(_SOURCE_SECRET)
    assert request.required

    payload = next(file.data for file in built.files if file.path == item.path)
    assert b"secret://source/warehouse-password" in payload
    assert b"actual-password" not in payload

    first = tmp_path / "first.roninbundle"
    second = tmp_path / "second.roninbundle"
    first_manifest = export_connection_bundle(connections, _WS, _CONNECTION, first)
    second_manifest = export_connection_bundle(connections, _WS, _CONNECTION, second)
    assert first_manifest == second_manifest
    assert first.read_bytes() == second.read_bytes()
    assert verify_bundle(first) == first_manifest


def test_connection_bundle_import_remaps_secret_and_retries_as_exact_noop(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    workspaces, connections = _stores(tmp_path / "target.sqlite3")

    first = commit_connection_bundle_import(
        bundle,
        workspaces,
        connections,
        _WS,
        resolutions=(_resolution(),),
        now=_NOW,
    )
    assert first.plan.disposition == "create"
    assert first.resolved_connection.secret_refs == (("password", _TARGET_SECRET),)
    assert connections.get_connection(_WS, _CONNECTION) == first.resolved_connection

    second = commit_connection_bundle_import(
        bundle,
        workspaces,
        connections,
        _WS,
        resolutions=(_resolution(),),
        now=_NOW,
    )
    assert second.plan.disposition == "existing"
    assert second.resolved_connection == first.resolved_connection


def test_connection_plan_treats_secret_uri_as_remappable_but_structure_as_fixed(
    tmp_path: Path,
) -> None:
    bundle = _export(tmp_path)
    workspaces, connections = _stores(tmp_path / "target.sqlite3")
    connections.create_connection(
        _WS,
        _definition(secret_ref=_TARGET_SECRET),
        now=_NOW,
    )
    compatible = plan_connection_bundle_import(bundle, workspaces, connections, _WS)
    assert compatible.disposition == "existing"

    other_workspaces, other_connections = _stores(tmp_path / "collision.sqlite3")
    other_connections.create_connection(
        _WS,
        _definition(name="Different connection"),
        now=_NOW,
    )
    collision = plan_connection_bundle_import(
        bundle,
        other_workspaces,
        other_connections,
        _WS,
    )
    assert collision.disposition == "collision"
    with pytest.raises(ConnectionBundleImportConflict, match="different portable structure"):
        commit_connection_bundle_import(
            bundle,
            other_workspaces,
            other_connections,
            _WS,
            resolutions=(_resolution(),),
            now=_NOW,
        )


def test_connection_bundle_import_requires_exact_secret_resolutions(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    workspaces, connections = _stores(tmp_path / "target.sqlite3")

    with pytest.raises(ConnectionBundleBindingError, match="remain unresolved"):
        commit_connection_bundle_import(bundle, workspaces, connections, _WS, now=_NOW)
    assert connections.get_connection(_WS, _CONNECTION) is None

    unknown = DeploymentBinding(
        "secret",
        "secret://source/other",
        "secret://target/other",
    )
    with pytest.raises(ConnectionBundleBindingError, match="was not requested"):
        commit_connection_bundle_import(
            bundle,
            workspaces,
            connections,
            _WS,
            resolutions=(unknown,),
            now=_NOW,
        )
    assert connections.get_connection(_WS, _CONNECTION) is None


def test_existing_connection_rejects_different_secret_remap_at_atomic_create(
    tmp_path: Path,
) -> None:
    bundle = _export(tmp_path)
    workspaces, connections = _stores(tmp_path / "target.sqlite3")
    connections.create_connection(
        _WS,
        _definition(secret_ref=_TARGET_SECRET),
        now=_NOW,
    )
    different = DeploymentBinding(
        "secret",
        str(_SOURCE_SECRET),
        "secret://target/different-password",
    )

    with pytest.raises(ConnectionConflict, match="already exists"):
        commit_connection_bundle_import(
            bundle,
            workspaces,
            connections,
            _WS,
            resolutions=(different,),
            now=_NOW,
        )
    assert connections.get_connection(_WS, _CONNECTION) == _definition(
        secret_ref=_TARGET_SECRET
    )
