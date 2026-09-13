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
from studio_core.bundle_inventory import BUNDLE_INVENTORY_PATH, BundleInventory, BundleInventoryObject
from studio_execution.bundle_import import UnsupportedBundleInventory, plan_project_bundle_import
from studio_execution.bundle_inventory import (
    INVENTORY_MEDIA_TYPE,
    PROJECT_BUNDLE_MEDIA_TYPE,
    export_project_bundle,
)
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, BundleIntegrityError, write_bundle
from studio_storage.bundle_payload import read_bundle_payload
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T09:20:00.000000Z")
_WS = WorkspaceId("workspace-1")
_PROJECT = ProjectId("project-1")


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
                    auth_ref="secret://git/project-auth",
                ),
            ),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


def _store(path: Path, *, manifest: ProjectManifest | None = None) -> SqliteWorkspaceStore:
    store = SqliteWorkspaceStore(path, migration_now=_NOW)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    if manifest is not None:
        store.register_project(_WS, manifest, now=_NOW)
    return store


def _export(tmp_path: Path) -> tuple[Path, ProjectManifest]:
    manifest = _manifest()
    source = _store(tmp_path / "source.sqlite3", manifest=manifest)
    bundle = tmp_path / "project.roninbundle"
    export_project_bundle(source, _WS, _PROJECT, bundle)
    return bundle, manifest


def test_import_plan_classifies_create_and_does_not_mutate_target(tmp_path: Path) -> None:
    bundle, manifest = _export(tmp_path)
    target = _store(tmp_path / "target.sqlite3")

    plan = plan_project_bundle_import(bundle, target, _WS)

    assert plan.disposition == "create"
    assert plan.project == manifest
    assert plan.project_id == _PROJECT
    assert plan.collision_reason is None
    assert plan.has_required_bindings
    assert len(plan.unresolved_bindings) == 1
    assert plan.unresolved_bindings[0].source_ref == "runtime-profile:python/3.11"
    assert target.list_projects(_WS) == ()


def test_import_plan_classifies_identical_target_as_noop(tmp_path: Path) -> None:
    bundle, manifest = _export(tmp_path)
    target = _store(tmp_path / "target.sqlite3", manifest=manifest)

    plan = plan_project_bundle_import(bundle, target, _WS)

    assert plan.disposition == "noop"
    assert plan.collision_reason is None
    assert target.get_project(_WS, _PROJECT) == manifest


def test_import_plan_reports_same_id_different_content_as_collision(tmp_path: Path) -> None:
    bundle, _manifest_value = _export(tmp_path)
    conflicting = _manifest("Different target project")
    target = _store(tmp_path / "target.sqlite3", manifest=conflicting)

    plan = plan_project_bundle_import(bundle, target, _WS)

    assert plan.disposition == "collision"
    assert plan.collision_reason == "project id already exists with different portable content"
    assert target.get_project(_WS, _PROJECT) == conflicting


def test_import_plan_rejects_inventory_identity_mismatch(tmp_path: Path) -> None:
    project = _manifest()
    object_path = "objects/project/project.json"
    inventory = BundleInventory(
        (BundleInventoryObject("project", "project:other", object_path),)
    )
    bundle = tmp_path / "mismatch.roninbundle"
    write_bundle(
        bundle,
        (
            BundleFile(
                BUNDLE_INVENTORY_PATH,
                INVENTORY_MEDIA_TYPE,
                inventory.to_json().encode("utf-8"),
            ),
            BundleFile(
                object_path,
                PROJECT_BUNDLE_MEDIA_TYPE,
                project.to_json().encode("utf-8"),
            ),
        ),
    )
    target = _store(tmp_path / "target.sqlite3")

    with pytest.raises(UnsupportedBundleInventory, match="logical identity"):
        plan_project_bundle_import(bundle, target, _WS)
    assert target.list_projects(_WS) == ()


def test_import_plan_rejects_unsupported_inventory_kind(tmp_path: Path) -> None:
    object_path = "objects/connection/connection.json"
    inventory = BundleInventory(
        (BundleInventoryObject("connection", "connection:source", object_path),)
    )
    bundle = tmp_path / "unsupported.roninbundle"
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
    target = _store(tmp_path / "target.sqlite3")

    with pytest.raises(UnsupportedBundleInventory, match="exactly one supported project"):
        plan_project_bundle_import(bundle, target, _WS)


def test_verified_payload_reader_enforces_in_memory_limit(tmp_path: Path) -> None:
    bundle, _manifest_value = _export(tmp_path)

    with pytest.raises(BundleIntegrityError, match="in-memory read limit"):
        read_bundle_payload(bundle, BUNDLE_INVENTORY_PATH, max_bytes=1)
