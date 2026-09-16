from __future__ import annotations

from dataclasses import replace

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
from studio_core.environments import (
    DeploymentBinding,
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_execution import (
    DeploymentBindingService,
    EnvironmentService,
    EnvironmentServiceConflict,
    EnvironmentServiceNotFound,
)

_NOW = "2026-09-14T08:50:00.000000Z"
_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("orders")
_ENV = EnvironmentId("prod")


class _WorkspaceStore:
    def __init__(self) -> None:
        self.workspaces: dict[WorkspaceId, Workspace] = {}
        self.projects: dict[tuple[WorkspaceId, ProjectId], ProjectManifest] = {}

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
        del now
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def replace_project(self, workspace_id, manifest, *, now):
        del now
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def get_project(self, workspace_id, project_id):
        return self.projects.get((workspace_id, project_id))

    def list_projects(self, workspace_id):
        return tuple(
            manifest
            for (found_workspace, _project_id), manifest in sorted(
                self.projects.items(), key=lambda item: item[0][1].value
            )
            if found_workspace == workspace_id
        )

    def unregister_project(self, workspace_id, project_id):
        return self.projects.pop((workspace_id, project_id), None) is not None


class _EnvironmentStore:
    def __init__(self) -> None:
        self.environments: dict[tuple[WorkspaceId, EnvironmentId], EnvironmentDefinition] = {}
        self.bindings: dict[
            tuple[WorkspaceId, ProjectId, EnvironmentId], ProjectEnvironmentBindings
        ] = {}
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def put_environment(self, workspace_id, environment, *, now):
        del now
        self._called("put_environment")
        self.environments[(workspace_id, environment.id)] = environment
        return environment

    def get_environment(self, workspace_id, environment_id):
        return self.environments.get((workspace_id, environment_id))

    def list_environments(self, workspace_id):
        return tuple(
            environment
            for (found_workspace, _environment_id), environment in sorted(
                self.environments.items(), key=lambda item: item[0][1].value
            )
            if found_workspace == workspace_id
        )

    def put_project_bindings(self, workspace_id, bindings, *, now):
        del now
        self._called("put_project_bindings")
        self.bindings[(workspace_id, bindings.project_id, bindings.environment_id)] = bindings
        return bindings

    def get_project_bindings(self, workspace_id, project_id, environment_id):
        return self.bindings.get((workspace_id, project_id, environment_id))


def _manifest() -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            id=_PROJECT,
            name="Orders",
            repositories=(
                RepositoryBinding(
                    "code",
                    "https://git.example.test/orders.git",
                    role="primary",
                ),
            ),
            execution=ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _stores(*, archived: bool = False, register_project: bool = True):
    workspaces = _WorkspaceStore()
    environments = _EnvironmentStore()
    workspaces.workspaces[_WS] = Workspace(
        _WS,
        "Workspace",
        state="archived" if archived else "active",
    )
    if register_project:
        workspaces.projects[(_WS, _PROJECT)] = _manifest()
    return workspaces, environments


def _bindings(target: str = "connection://prod-warehouse") -> ProjectEnvironmentBindings:
    return ProjectEnvironmentBindings(
        _PROJECT,
        _ENV,
        (
            DeploymentBinding("connection", "warehouse", target),
            DeploymentBinding("secret", "warehouse-password", "secret://env/WAREHOUSE_PASSWORD"),
        ),
    )


def test_environment_create_is_idempotent_and_conflicting_reuse_is_stable() -> None:
    workspaces, store = _stores()
    service = EnvironmentService(workspaces, store)
    environment = EnvironmentDefinition(_ENV, "Production")

    assert service.create(_WS, environment, now=_NOW) == environment
    assert service.create(_WS, environment, now=_NOW) == environment
    assert store.calls["put_environment"] == 1

    with pytest.raises(EnvironmentServiceConflict, match="different intent"):
        service.create(_WS, EnvironmentDefinition(_ENV, "Different"), now=_NOW)
    assert store.calls["put_environment"] == 1


def test_environment_replace_disable_and_reads_are_idempotent() -> None:
    workspaces, store = _stores()
    service = EnvironmentService(workspaces, store)
    original = service.create(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)

    assert service.replace(_WS, original, now=_NOW) == original
    assert store.calls["put_environment"] == 1

    changed = EnvironmentDefinition(_ENV, "Production", "Primary deployment")
    assert service.replace(_WS, changed, now=_NOW) == changed
    assert store.calls["put_environment"] == 2

    disabled = service.disable(_WS, _ENV, now=_NOW)
    assert disabled.disabled
    assert service.disable(_WS, _ENV, now=_NOW) == disabled
    assert store.calls["put_environment"] == 3
    assert service.get(_WS, _ENV) == disabled
    assert service.list(_WS) == (disabled,)


def test_environment_reads_survive_archival_but_mutations_fail_before_store_write() -> None:
    workspaces, store = _stores()
    service = EnvironmentService(workspaces, store)
    environment = service.create(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)
    writes = store.calls["put_environment"]
    workspaces.workspaces[_WS] = replace(workspaces.workspaces[_WS], state="archived")

    assert service.get(_WS, _ENV) == environment
    assert service.list(_WS) == (environment,)

    with pytest.raises(EnvironmentServiceConflict, match="archived"):
        service.create(_WS, EnvironmentDefinition(EnvironmentId("dev"), "Development"), now=_NOW)
    with pytest.raises(EnvironmentServiceConflict, match="archived"):
        service.replace(_WS, EnvironmentDefinition(_ENV, "Changed"), now=_NOW)
    with pytest.raises(EnvironmentServiceConflict, match="archived"):
        service.disable(_WS, _ENV, now=_NOW)
    assert store.calls["put_environment"] == writes


def test_environment_missing_workspace_and_environment_use_stable_not_found() -> None:
    workspaces = _WorkspaceStore()
    store = _EnvironmentStore()
    service = EnvironmentService(workspaces, store)

    with pytest.raises(EnvironmentServiceNotFound, match="workspace not found"):
        service.list(_WS)
    with pytest.raises(EnvironmentServiceNotFound, match="workspace not found"):
        service.create(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)

    workspaces.workspaces[_WS] = Workspace(_WS, "Workspace")
    with pytest.raises(EnvironmentServiceNotFound, match="environment not found"):
        service.get(_WS, _ENV)
    with pytest.raises(EnvironmentServiceNotFound, match="environment not found"):
        service.replace(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)
    assert store.calls.get("put_environment", 0) == 0


def test_binding_put_is_idempotent_and_changed_intent_replaces_once() -> None:
    workspaces, store = _stores()
    environments = EnvironmentService(workspaces, store)
    environments.create(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)
    service = DeploymentBindingService(workspaces, store)
    first = _bindings()

    assert service.put(_WS, first, now=_NOW) == first
    assert service.put(_WS, first, now=_NOW) == first
    assert store.calls["put_project_bindings"] == 1

    changed = _bindings("connection://prod-warehouse-v2")
    assert service.put(_WS, changed, now=_NOW) == changed
    assert store.calls["put_project_bindings"] == 2
    assert service.get(_WS, _PROJECT, _ENV) == changed
    assert changed.resolve("secret", "warehouse-password") == "secret://env/WAREHOUSE_PASSWORD"


def test_binding_preflights_project_environment_and_disabled_state_before_write() -> None:
    workspaces, store = _stores(register_project=False)
    environment_service = EnvironmentService(workspaces, store)
    environment_service.create(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)
    service = DeploymentBindingService(workspaces, store)

    with pytest.raises(EnvironmentServiceNotFound, match="project not found"):
        service.put(_WS, _bindings(), now=_NOW)
    assert store.calls.get("put_project_bindings", 0) == 0

    workspaces.projects[(_WS, _PROJECT)] = _manifest()
    store.environments.pop((_WS, _ENV))
    with pytest.raises(EnvironmentServiceNotFound, match="environment not found"):
        service.put(_WS, _bindings(), now=_NOW)
    assert store.calls.get("put_project_bindings", 0) == 0

    store.environments[(_WS, _ENV)] = EnvironmentDefinition(
        _ENV,
        "Production",
        state="disabled",
    )
    with pytest.raises(EnvironmentServiceConflict, match="disabled"):
        service.put(_WS, _bindings(), now=_NOW)
    assert store.calls.get("put_project_bindings", 0) == 0


def test_binding_read_survives_disable_and_workspace_archive() -> None:
    workspaces, store = _stores()
    environments = EnvironmentService(workspaces, store)
    environments.create(_WS, EnvironmentDefinition(_ENV, "Production"), now=_NOW)
    service = DeploymentBindingService(workspaces, store)
    bindings = service.put(_WS, _bindings(), now=_NOW)

    environments.disable(_WS, _ENV, now=_NOW)
    assert service.get(_WS, _PROJECT, _ENV) == bindings

    workspaces.workspaces[_WS] = replace(workspaces.workspaces[_WS], state="archived")
    assert service.get(_WS, _PROJECT, _ENV) == bindings
    writes = store.calls["put_project_bindings"]
    with pytest.raises(EnvironmentServiceConflict, match="archived"):
        service.put(_WS, bindings, now=_NOW)
    assert store.calls["put_project_bindings"] == writes


def test_binding_missing_uses_stable_not_found() -> None:
    workspaces, store = _stores()
    EnvironmentService(workspaces, store).create(
        _WS,
        EnvironmentDefinition(_ENV, "Production"),
        now=_NOW,
    )
    service = DeploymentBindingService(workspaces, store)

    with pytest.raises(EnvironmentServiceNotFound, match="bindings not found"):
        service.get(_WS, _PROJECT, _ENV)
