from __future__ import annotations

from dataclasses import replace

import pytest
from studio_core import (
    ConnectionDefinition,
    ConnectionId,
    SecretRef,
    Workspace,
    WorkspaceId,
)
from studio_execution.connection_service import (
    ConnectionService,
    ConnectionServiceConflict,
    ConnectionServiceNotFound,
)

_NOW = "2026-09-14T08:52:00.000000Z"
_WS = WorkspaceId("workspace-1")
_CONNECTION = ConnectionId("warehouse")


class _WorkspaceStore:
    def __init__(self) -> None:
        self.workspaces: dict[WorkspaceId, Workspace] = {}

    def create_workspace(self, workspace, *, now):
        del now
        self.workspaces[workspace.id] = workspace
        return workspace

    def get_workspace(self, workspace_id):
        return self.workspaces.get(workspace_id)

    def list_workspaces(self):
        return tuple(sorted(self.workspaces.values(), key=lambda item: item.id.value))

    def update_workspace(self, workspace, *, now):
        del now
        self.workspaces[workspace.id] = workspace
        return workspace

    def register_project(self, workspace_id, manifest, *, now):
        raise AssertionError("project operations are not used by ConnectionService")

    def replace_project(self, workspace_id, manifest, *, now):
        raise AssertionError("project operations are not used by ConnectionService")

    def get_project(self, workspace_id, project_id):
        raise AssertionError("project operations are not used by ConnectionService")

    def list_projects(self, workspace_id):
        raise AssertionError("project operations are not used by ConnectionService")

    def unregister_project(self, workspace_id, project_id):
        raise AssertionError("project operations are not used by ConnectionService")


class _ConnectionStore:
    def __init__(self) -> None:
        self.connections: dict[tuple[WorkspaceId, ConnectionId], ConnectionDefinition] = {}
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def create_connection(self, workspace_id, definition, *, now):
        del now
        self._called("create_connection")
        self.connections[(workspace_id, definition.id)] = definition
        return definition

    def replace_connection(self, workspace_id, definition, *, now):
        del now
        self._called("replace_connection")
        self.connections[(workspace_id, definition.id)] = definition
        return definition

    def get_connection(self, workspace_id, connection_id):
        return self.connections.get((workspace_id, connection_id))

    def list_connections(self, workspace_id):
        return tuple(
            definition
            for (found_workspace, _connection_id), definition in sorted(
                self.connections.items(), key=lambda item: item[0][1].value
            )
            if found_workspace == workspace_id
        )

    def delete_connection(self, workspace_id, connection_id):
        self._called("delete_connection")
        return self.connections.pop((workspace_id, connection_id), None) is not None


def _definition(*, name: str = "Warehouse", host: str = "db.internal") -> ConnectionDefinition:
    return ConnectionDefinition(
        id=_CONNECTION,
        name=name,
        connector_id="postgresql",
        options=(("host", host), ("database", "analytics")),
        secret_refs=(("password", SecretRef("secret://workspace/warehouse-password")),),
    )


def _stores(*, archived: bool = False):
    workspaces = _WorkspaceStore()
    workspaces.workspaces[_WS] = Workspace(
        _WS,
        "Workspace",
        state="archived" if archived else "active",
    )
    return workspaces, _ConnectionStore()


def test_create_is_idempotent_and_conflicting_reuse_is_stable() -> None:
    workspaces, store = _stores()
    service = ConnectionService(workspaces, store)
    definition = _definition()

    assert service.create(_WS, definition, now=_NOW) == definition
    assert service.create(_WS, definition, now=_NOW) == definition
    assert store.calls["create_connection"] == 1

    with pytest.raises(ConnectionServiceConflict, match="different intent"):
        service.create(_WS, _definition(name="Different"), now=_NOW)
    assert store.calls["create_connection"] == 1


def test_get_list_and_secret_refs_preserve_canonical_definition() -> None:
    workspaces, store = _stores()
    service = ConnectionService(workspaces, store)
    definition = service.create(_WS, _definition(), now=_NOW)

    assert service.get(_WS, _CONNECTION) == definition
    assert service.list(_WS) == (definition,)
    assert definition.to_payload()["secret_refs"] == {
        "password": "secret://workspace/warehouse-password"
    }
    assert "warehouse-password" in str(definition.secret_refs[0][1])
    assert all("plaintext" not in value for _key, value in definition.options)


def test_replace_is_idempotent_and_changed_intent_writes_once() -> None:
    workspaces, store = _stores()
    service = ConnectionService(workspaces, store)
    original = service.create(_WS, _definition(), now=_NOW)

    assert service.replace(_WS, original, now=_NOW) == original
    assert store.calls.get("replace_connection", 0) == 0

    changed = _definition(host="db-v2.internal")
    assert service.replace(_WS, changed, now=_NOW) == changed
    assert store.calls["replace_connection"] == 1
    assert service.get(_WS, _CONNECTION) == changed


def test_delete_succeeds_once_and_missing_connection_is_stable() -> None:
    workspaces, store = _stores()
    service = ConnectionService(workspaces, store)
    service.create(_WS, _definition(), now=_NOW)

    service.delete(_WS, _CONNECTION)
    assert store.calls["delete_connection"] == 1

    with pytest.raises(ConnectionServiceNotFound, match="connection not found"):
        service.get(_WS, _CONNECTION)
    with pytest.raises(ConnectionServiceNotFound, match="connection not found"):
        service.delete(_WS, _CONNECTION)
    assert store.calls["delete_connection"] == 1


def test_missing_workspace_and_connection_use_stable_not_found() -> None:
    workspaces = _WorkspaceStore()
    store = _ConnectionStore()
    service = ConnectionService(workspaces, store)

    with pytest.raises(ConnectionServiceNotFound, match="workspace not found"):
        service.list(_WS)
    with pytest.raises(ConnectionServiceNotFound, match="workspace not found"):
        service.create(_WS, _definition(), now=_NOW)
    assert store.calls.get("create_connection", 0) == 0

    workspaces.workspaces[_WS] = Workspace(_WS, "Workspace")
    with pytest.raises(ConnectionServiceNotFound, match="connection not found"):
        service.get(_WS, _CONNECTION)
    with pytest.raises(ConnectionServiceNotFound, match="connection not found"):
        service.replace(_WS, _definition(), now=_NOW)
    assert store.calls.get("replace_connection", 0) == 0


def test_archived_workspace_preserves_reads_but_blocks_mutations_before_store_write() -> None:
    workspaces, store = _stores()
    service = ConnectionService(workspaces, store)
    definition = service.create(_WS, _definition(), now=_NOW)
    workspaces.workspaces[_WS] = replace(workspaces.workspaces[_WS], state="archived")

    assert service.get(_WS, _CONNECTION) == definition
    assert service.list(_WS) == (definition,)

    create_calls = store.calls["create_connection"]
    with pytest.raises(ConnectionServiceConflict, match="archived"):
        service.create(
            _WS,
            ConnectionDefinition(
                ConnectionId("other"),
                "Other",
                "postgresql",
            ),
            now=_NOW,
        )
    with pytest.raises(ConnectionServiceConflict, match="archived"):
        service.replace(_WS, _definition(host="blocked.internal"), now=_NOW)
    with pytest.raises(ConnectionServiceConflict, match="archived"):
        service.delete(_WS, _CONNECTION)

    assert store.calls["create_connection"] == create_calls
    assert store.calls.get("replace_connection", 0) == 0
    assert store.calls.get("delete_connection", 0) == 0
