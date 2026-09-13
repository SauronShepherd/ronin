from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    Workspace,
    WorkspaceId,
)
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_execution.bundle_catalog import (
    INVENTORY_MEDIA_TYPE,
    CatalogBundleTargetError,
    UnsupportedCatalogBundle,
    build_catalog_bundle_inventory,
    export_catalog_bundle,
    plan_catalog_bundle_import,
)
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, verify_bundle, write_bundle
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T10:10:00.000000Z")
_WS = WorkspaceId("workspace-1")
_SOURCE = AssetId("asset/source")
_DERIVED = AssetId("asset/derived")
_SOURCE_REF = AssetRef(_SOURCE, AssetVersion("1"))
_DERIVED_REF = AssetRef(_DERIVED, AssetVersion("1"))


def _assets() -> tuple[CatalogAsset, CatalogAsset]:
    return (
        CatalogAsset(_SOURCE, "table", "Source", tags=("raw",)),
        CatalogAsset(_DERIVED, "table", "Derived", tags=("curated",)),
    )


def _revisions() -> tuple[AssetRevision, AssetRevision]:
    return (
        AssetRevision(_SOURCE_REF, metadata=(("owner", "data"),)),
        AssetRevision(_DERIVED_REF, metadata=(("owner", "analytics"),)),
    )


def _lineage() -> LineageEdge:
    return LineageEdge(
        _SOURCE_REF,
        _DERIVED_REF,
        operation="transform",
        mode="observed",
        execution_ref="job:example",
    )


def _stores(path: Path) -> tuple[SqliteWorkspaceStore, SqliteCatalogStore]:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    return workspaces, SqliteCatalogStore(path, migration_now=_NOW)


def _populate(catalog: SqliteCatalogStore) -> None:
    source, derived = _assets()
    source_revision, derived_revision = _revisions()
    catalog.create_asset(_WS, source, now=_NOW)
    catalog.create_asset(_WS, derived, now=_NOW)
    catalog.put_revision(_WS, source_revision, now=_NOW)
    catalog.put_revision(_WS, derived_revision, now=_NOW)
    catalog.put_lineage(_WS, _lineage(), now=_NOW)


def _export(tmp_path: Path) -> Path:
    _workspaces, catalog = _stores(tmp_path / "source.sqlite3")
    _populate(catalog)
    bundle = tmp_path / "catalog.roninbundle"
    export_catalog_bundle(catalog, _WS, (_SOURCE_REF, _DERIVED_REF), bundle)
    return bundle


def test_catalog_inventory_exports_selected_subgraph_with_dependencies(tmp_path: Path) -> None:
    _workspaces, catalog = _stores(tmp_path / "source.sqlite3")
    _populate(catalog)

    built = build_catalog_bundle_inventory(
        catalog,
        _WS,
        (_SOURCE_REF, _DERIVED_REF),
    )

    assert len(built.inventory.objects) == 5
    assert built.inventory.unresolved_bindings == ()
    assets = [item for item in built.inventory.objects if item.kind == "catalog_asset"]
    revisions = [
        item for item in built.inventory.objects if item.kind == "catalog_revision"
    ]
    lineage = [item for item in built.inventory.objects if item.kind == "catalog_lineage"]
    assert len(assets) == 2
    assert len(revisions) == 2
    assert len(lineage) == 1
    asset_refs = {item.logical_ref for item in assets}
    revision_refs = {item.logical_ref for item in revisions}
    assert all(len(item.dependencies) == 1 for item in revisions)
    assert all(item.dependencies[0] in asset_refs for item in revisions)
    assert set(lineage[0].dependencies) == revision_refs
    assert all(item.path.startswith("objects/catalog/") for item in built.inventory.objects)
    assert all(str(_SOURCE) not in item.path for item in built.inventory.objects)
    assert all(str(_DERIVED) not in item.path for item in built.inventory.objects)


def test_catalog_bundle_export_is_byte_deterministic_and_verifiable(tmp_path: Path) -> None:
    _workspaces, catalog = _stores(tmp_path / "source.sqlite3")
    _populate(catalog)
    first = tmp_path / "first.roninbundle"
    second = tmp_path / "second.roninbundle"

    first_manifest = export_catalog_bundle(
        catalog,
        _WS,
        (_SOURCE_REF, _DERIVED_REF),
        first,
    )
    second_manifest = export_catalog_bundle(
        catalog,
        _WS,
        (_DERIVED_REF, _SOURCE_REF),
        second,
    )

    assert first_manifest == second_manifest
    assert first.read_bytes() == second.read_bytes()
    assert verify_bundle(first) == first_manifest


def test_catalog_plan_orders_dependencies_and_does_not_mutate_target(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    workspaces, catalog = _stores(tmp_path / "target.sqlite3")

    plan = plan_catalog_bundle_import(bundle, workspaces, catalog, _WS)

    positions = {item.logical_ref: index for index, item in enumerate(plan.objects)}
    for item in plan.objects:
        assert item.disposition == "create"
        for dependency in item.dependencies:
            assert positions[dependency] < positions[item.logical_ref]
    assert not plan.has_collisions
    assert catalog.list_assets(_WS) == ()


def test_catalog_plan_identical_target_is_all_noop(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    workspaces, catalog = _stores(tmp_path / "target.sqlite3")
    _populate(catalog)

    plan = plan_catalog_bundle_import(bundle, workspaces, catalog, _WS)

    assert plan.objects
    assert all(item.disposition == "noop" for item in plan.objects)
    assert not plan.has_collisions


def test_catalog_plan_reports_asset_collision(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    workspaces, catalog = _stores(tmp_path / "target.sqlite3")
    catalog.create_asset(
        _WS,
        CatalogAsset(_SOURCE, "table", "Different source", tags=("raw",)),
        now=_NOW,
    )

    plan = plan_catalog_bundle_import(bundle, workspaces, catalog, _WS)

    assert plan.has_collisions
    collision = next(item for item in plan.objects if item.disposition == "collision")
    assert collision.kind == "catalog_asset"
    assert collision.collision_reason is not None


def test_catalog_selection_excludes_lineage_when_endpoint_is_not_selected(
    tmp_path: Path,
) -> None:
    _workspaces, catalog = _stores(tmp_path / "source.sqlite3")
    _populate(catalog)

    built = build_catalog_bundle_inventory(catalog, _WS, (_SOURCE_REF,))

    assert [item.kind for item in built.inventory.objects] == [
        "catalog_asset",
        "catalog_revision",
    ]


def test_catalog_plan_rejects_revision_dependency_that_does_not_match_payload(
    tmp_path: Path,
) -> None:
    _workspaces, source_catalog = _stores(tmp_path / "source.sqlite3")
    _populate(source_catalog)
    built = build_catalog_bundle_inventory(
        source_catalog,
        _WS,
        (_SOURCE_REF, _DERIVED_REF),
    )
    assets = [item for item in built.inventory.objects if item.kind == "catalog_asset"]
    revisions = [
        item for item in built.inventory.objects if item.kind == "catalog_revision"
    ]
    source_revision = next(
        item
        for item in revisions
        if AssetRevision.from_json(
            next(file.data for file in built.files if file.path == item.path).decode("utf-8")
        ).ref
        == _SOURCE_REF
    )
    wrong_asset_ref = next(
        item.logical_ref
        for item in assets
        if item.logical_ref != source_revision.dependencies[0]
    )
    tampered_objects = tuple(
        BundleInventoryObject(
            item.kind,
            item.logical_ref,
            item.path,
            dependencies=(wrong_asset_ref,) if item is source_revision else item.dependencies,
            binding_requests=item.binding_requests,
        )
        for item in built.inventory.objects
    )
    inventory = BundleInventory(tampered_objects)
    bundle = tmp_path / "tampered.roninbundle"
    files = tuple(
        BundleFile(
            file.path,
            file.media_type,
            inventory.to_json().encode("utf-8")
            if file.path == BUNDLE_INVENTORY_PATH
            else file.data,
        )
        for file in built.files
    )
    write_bundle(bundle, files)
    workspaces, catalog = _stores(tmp_path / "target.sqlite3")

    with pytest.raises(UnsupportedCatalogBundle, match="dependency"):
        plan_catalog_bundle_import(bundle, workspaces, catalog, _WS)
    assert catalog.list_assets(_WS) == ()


def test_catalog_plan_rejects_missing_or_archived_target_workspace(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    missing_path = tmp_path / "missing.sqlite3"
    missing_catalog = SqliteCatalogStore(missing_path, migration_now=_NOW)
    missing_workspaces = SqliteWorkspaceStore(missing_path, migration_now=_NOW)
    with pytest.raises(CatalogBundleTargetError, match="does not exist"):
        plan_catalog_bundle_import(bundle, missing_workspaces, missing_catalog, _WS)

    archived_workspaces, archived_catalog = _stores(tmp_path / "archived.sqlite3")
    archived_workspaces.update_workspace(
        Workspace(_WS, "Workspace", state="archived"),
        now=_NOW,
    )
    with pytest.raises(CatalogBundleTargetError, match="archived"):
        plan_catalog_bundle_import(bundle, archived_workspaces, archived_catalog, _WS)
