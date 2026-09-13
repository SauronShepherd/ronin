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
from studio_core.bundle_inventory import BundleInventory, BundleInventoryObject
from studio_execution.bundle_inventory import (
    build_project_bundle_inventory,
    export_project_bundle,
)
from studio_orchestrator import Instant
from studio_storage.bundle import verify_bundle
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T09:10:00.000000Z")
_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("team/project with spaces")


def _store(tmp_path: Path) -> SqliteWorkspaceStore:
    path = tmp_path / "ronin.sqlite3"
    store = SqliteWorkspaceStore(path, migration_now=_NOW)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    project = Project(
        _PROJECT,
        "Portable project",
        (
            RepositoryBinding(
                "code",
                "https://git.example.test/team/repo.git",
                role="primary",
                auth_ref="secret://git/project-auth",
            ),
        ),
        ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
    )
    store.register_project(_WS, ProjectManifest.from_project(project), now=_NOW)
    return store


def test_bundle_inventory_rejects_ambiguous_refs_and_unknown_dependencies() -> None:
    first = BundleInventoryObject("project", "object:1", "objects/a.json")
    second = BundleInventoryObject("connection", "object:1", "objects/b.json")
    with pytest.raises(ValueError, match="logical refs"):
        BundleInventory((first, second))

    dependent = BundleInventoryObject(
        "project",
        "project:1",
        "objects/project.json",
        dependencies=("missing:1",),
    )
    with pytest.raises(ValueError, match="unknown dependencies"):
        BundleInventory((dependent,))


def test_project_inventory_uses_safe_payload_path_and_runtime_binding(tmp_path: Path) -> None:
    store = _store(tmp_path)
    built = build_project_bundle_inventory(store, _WS, _PROJECT)

    assert len(built.inventory.objects) == 1
    item = built.inventory.objects[0]
    assert item.kind == "project"
    assert item.logical_ref == f"project:{_PROJECT}"
    assert item.path.startswith("objects/project/")
    assert str(_PROJECT) not in item.path
    assert len(built.inventory.unresolved_bindings) == 1
    binding = built.inventory.unresolved_bindings[0]
    assert binding.kind == "runtime"
    assert binding.source_ref == "runtime-profile:python/3.11"
    assert binding.required

    project_file = next(file for file in built.files if file.path == item.path)
    assert b"project-auth" not in project_file.data
    parsed = ProjectManifest.from_json(project_file.data.decode("utf-8"))
    assert parsed.project.id == _PROJECT
    assert parsed.project.repositories[0].auth_ref is None


def test_project_bundle_export_is_byte_deterministic_and_verifiable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = tmp_path / "first.roninbundle"
    second = tmp_path / "second.roninbundle"

    first_manifest = export_project_bundle(store, _WS, _PROJECT, first)
    second_manifest = export_project_bundle(store, _WS, _PROJECT, second)

    assert first_manifest == second_manifest
    assert first.read_bytes() == second.read_bytes()
    verified = verify_bundle(first)
    assert verified == first_manifest
    assert {entry.path for entry in verified.entries} == {
        file.path for file in build_project_bundle_inventory(store, _WS, _PROJECT).files
    }
