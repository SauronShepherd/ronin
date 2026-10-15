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


def test_project_archive_is_persisted_and_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert len(store.list_projects(_WS)) == 1
    assert store.archive_project(_WS, _PROJECT, now=Instant("2026-09-13T09:11:00.000000Z")) is True
    assert store.list_projects(_WS) == ()
    assert store.get_project(_WS, _PROJECT) is not None
    assert store.archive_project(_WS, _PROJECT, now=Instant("2026-09-13T09:12:00.000000Z")) is False


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


def test_bundle_inventory_round_trip_preserves_semantic_digest() -> None:
    inventory = BundleInventory(
        (
            BundleInventoryObject("connection", "connection:db", "objects/db.json"),
            BundleInventoryObject(
                "project",
                "project:orders",
                "objects/project.json",
                dependencies=("connection:db",),
            ),
        )
    )
    restored = BundleInventory.from_json(inventory.to_json())
    assert restored == inventory
    assert restored.digest == inventory.digest


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "./objects.json",
        "objects/../project.json",
        "objects\\project.json",
        "/objects.json",
    ],
)
def test_bundle_inventory_rejects_unsafe_object_paths(path: str) -> None:
    with pytest.raises(ValueError, match="bundle inventory path"):
        BundleInventoryObject("project", "project:1", path)


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("objects//project.json", "unsafe components"),
        ("objects/./project.json", "unsafe components"),
        ("objects/../project.json", "unsafe components"),
        ("objects\\project.json", "relative and use forward slashes"),
        ("/objects/project.json", "relative and use forward slashes"),
        ("ronin-inventory.json", "must not reuse the inventory path"),
    ],
)
def test_bundle_inventory_reports_each_unsafe_path_reason(path: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        BundleInventoryObject("project", "project:1", path)


@pytest.mark.parametrize(
    "value",
    ["", " ", " project", "project ", "project\njson", "project\rjson", "project\x00json"],
)
def test_bundle_inventory_rejects_non_canonical_identity_text(value: str) -> None:
    with pytest.raises(ValueError, match="non-empty, trimmed, and single-line"):
        BundleInventoryObject(value, "project:1", "objects/project.json")


def test_bundle_inventory_rejects_duplicate_dependencies_and_reserved_inventory_path() -> None:
    with pytest.raises(ValueError, match="dependencies must be unique"):
        BundleInventoryObject(
            "project", "project:1", "objects/project.json", dependencies=("x:1", "x:1")
        )
    with pytest.raises(ValueError, match="must not reuse"):
        BundleInventoryObject("project", "project:1", "ronin-inventory.json")


def test_bundle_inventory_unresolved_bindings_are_unique_and_sorted() -> None:
    from studio_core.portability import BindingRequest

    first = BindingRequest("runtime", "runtime:python", True, "python")
    second = BindingRequest("secret", "secret:git", False, "git")
    inventory = BundleInventory(
        (
            BundleInventoryObject("a", "a:1", "objects/a.json", binding_requests=(second, first)),
            BundleInventoryObject("b", "b:1", "objects/b.json", binding_requests=(first,)),
        )
    )
    assert inventory.unresolved_bindings == tuple(sorted((first, second)))
