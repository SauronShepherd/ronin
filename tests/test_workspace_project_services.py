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
from studio_execution import (
    ProjectService,
    WorkspaceService,
    WorkspaceServiceConflict,
    WorkspaceServiceNotFound,
)

_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("project-1")
_NOW = "2026-09-14T04:15:00.000000Z"


class _Store:
    def __init__(self) -> None:
        self.workspaces: dict[WorkspaceId, Workspace] = {}
        self.projects: dict[tuple[WorkspaceId, ProjectId], ProjectManifest] = {}
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def create_workspace(self, workspace, *, now):
        del now
        self._called("create_workspace")
        self.workspaces[workspace.id] = workspace
        return workspace

    def get_workspace(self, workspace_id):
        return self.workspaces.get(workspace_id)

    def list_workspaces(self):
        return tuple(sorted(self.workspaces.values(), key=lambda item: item.id.value))

    def update_workspace(self, workspace, *, now):
        del now
        self._called("update_workspace")
        self.workspaces[workspace.id] = workspace
        return workspace

    def register_project(self, workspace_id, manifest, *, now):
        del now
        self._called("register_project")
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def replace_project(self, workspace_id, manifest, *, now):
        del now
        self._called("replace_project")
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
        self._called("unregister_project")
        return self.projects.pop((workspace_id, project_id), None) is not None


def _manifest(name: str = "Project") -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            _PROJECT,
            name,
            (
                RepositoryBinding(
                    "code",
                    "https://git.example.test/team/project.git",
                    role="primary",
                ),
            ),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def test_workspace_create_is_idempotent_and_conflicting_reuse_fails() -> None:
    store = _Store()
    service = WorkspaceService(store)
    workspace = Workspace(_WS, "Workspace")

    assert service.create(workspace, now=_NOW) == workspace
    assert service.create(workspace, now=_NOW) == workspace
    assert store.calls["create_workspace"] == 1

    with pytest.raises(WorkspaceServiceConflict, match="already exists"):
        service.create(Workspace(_WS, "Different"), now=_NOW)
    assert store.calls["create_workspace"] == 1


def test_workspace_update_archive_and_read_contract() -> None:
    store = _Store()
    service = WorkspaceService(store)
    service.create(Workspace(_WS, "Workspace", "Original"), now=_NOW)

    unchanged = service.update(_WS, name="Workspace", description="Original", now=_NOW)
    assert unchanged.description == "Original"
    assert store.calls.get("update_workspace", 0) == 0

    updated = service.update(_WS, name="Renamed", description="Updated", now=_NOW)
    assert updated.name == "Renamed"
    assert store.calls["update_workspace"] == 1

    archived = service.archive(_WS, now=_NOW)
    assert archived.archived
    assert service.archive(_WS, now=_NOW) == archived
    assert store.calls["update_workspace"] == 2
    assert service.get(_WS) == archived
    assert service.list() == (archived,)

    with pytest.raises(WorkspaceServiceConflict, match="archived"):
        service.update(_WS, name="No", description=None, now=_NOW)
    assert store.calls["update_workspace"] == 2


def test_workspace_missing_operations_use_stable_not_found() -> None:
    service = WorkspaceService(_Store())
    with pytest.raises(WorkspaceServiceNotFound, match="workspace not found"):
        service.get(_WS)
    with pytest.raises(WorkspaceServiceNotFound, match="workspace not found"):
        service.update(_WS, name="Missing", description=None, now=_NOW)
    with pytest.raises(WorkspaceServiceNotFound, match="workspace not found"):
        service.archive(_WS, now=_NOW)


def test_project_registration_is_idempotent_and_conflicting_reuse_fails() -> None:
    store = _Store()
    WorkspaceService(store).create(Workspace(_WS, "Workspace"), now=_NOW)
    service = ProjectService(store)
    manifest = _manifest()

    assert service.register(_WS, manifest, now=_NOW) == manifest
    assert service.register(_WS, manifest, now=_NOW) == manifest
    assert store.calls["register_project"] == 1

    with pytest.raises(WorkspaceServiceConflict, match="different intent"):
        service.register(_WS, _manifest("Different"), now=_NOW)
    assert store.calls["register_project"] == 1


def test_project_replace_unregister_and_archived_read_contract() -> None:
    store = _Store()
    workspaces = WorkspaceService(store)
    workspaces.create(Workspace(_WS, "Workspace"), now=_NOW)
    projects = ProjectService(store)
    first = projects.register(_WS, _manifest(), now=_NOW)

    assert projects.replace(_WS, first, now=_NOW) == first
    assert store.calls.get("replace_project", 0) == 0

    changed = _manifest("Changed")
    assert projects.replace(_WS, changed, now=_NOW) == changed
    assert store.calls["replace_project"] == 1
    assert projects.get(_WS, _PROJECT) == changed

    archived = workspaces.archive(_WS, now=_NOW)
    assert archived.archived
    assert projects.get(_WS, _PROJECT) == changed
    assert projects.list(_WS) == (changed,)

    with pytest.raises(WorkspaceServiceConflict, match="archived"):
        projects.replace(_WS, _manifest("Blocked"), now=_NOW)
    with pytest.raises(WorkspaceServiceConflict, match="archived"):
        projects.unregister(_WS, _PROJECT)
    assert store.calls["replace_project"] == 1
    assert store.calls.get("unregister_project", 0) == 0

    store.workspaces[_WS] = replace(archived, state="active")
    projects.unregister(_WS, _PROJECT)
    assert store.calls["unregister_project"] == 1
    with pytest.raises(WorkspaceServiceNotFound, match="project not found"):
        projects.get(_WS, _PROJECT)


def test_project_mutations_fail_before_store_write_for_missing_or_archived_workspace() -> None:
    store = _Store()
    projects = ProjectService(store)

    with pytest.raises(WorkspaceServiceNotFound, match="workspace not found"):
        projects.register(_WS, _manifest(), now=_NOW)
    assert store.calls.get("register_project", 0) == 0

    store.workspaces[_WS] = Workspace(_WS, "Archived", state="archived")
    with pytest.raises(WorkspaceServiceConflict, match="archived"):
        projects.register(_WS, _manifest(), now=_NOW)
    assert store.calls.get("register_project", 0) == 0


def test_project_missing_replace_and_unregister_use_stable_not_found() -> None:
    store = _Store()
    WorkspaceService(store).create(Workspace(_WS, "Workspace"), now=_NOW)
    projects = ProjectService(store)

    with pytest.raises(WorkspaceServiceNotFound, match="project not found"):
        projects.get(_WS, _PROJECT)
    with pytest.raises(WorkspaceServiceNotFound, match="project not found"):
        projects.replace(_WS, _manifest(), now=_NOW)
    with pytest.raises(WorkspaceServiceNotFound, match="project not found"):
        projects.unregister(_WS, _PROJECT)
    assert store.calls.get("replace_project", 0) == 0
    assert store.calls.get("unregister_project", 0) == 0
