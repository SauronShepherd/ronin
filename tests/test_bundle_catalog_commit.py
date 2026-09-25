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
from studio_execution.bundle_catalog import export_catalog_bundle
from studio_execution.bundle_catalog_commit import commit_catalog_bundle_import
from studio_orchestrator import Instant
from studio_storage.bundle_catalog_import import SqliteCatalogBundleImportStore
from studio_storage.bundle_catalog_import_port import CatalogBundleImportConflict

_NOW = Instant("2026-09-13T10:20:00.000000Z")
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


def _store(path: Path) -> SqliteCatalogBundleImportStore:
    store = SqliteCatalogBundleImportStore(path, migration_now=_NOW)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    return store


def _populate(store: SqliteCatalogBundleImportStore) -> None:
    source, derived = _assets()
    source_revision, derived_revision = _revisions()
    store.create_asset(_WS, source, now=_NOW)
    store.create_asset(_WS, derived, now=_NOW)
    store.put_revision(_WS, source_revision, now=_NOW)
    store.put_revision(_WS, derived_revision, now=_NOW)
    store.put_lineage(_WS, _lineage(), now=_NOW)


def _export(tmp_path: Path) -> Path:
    source = _store(tmp_path / "source.sqlite3")
    _populate(source)
    bundle = tmp_path / "catalog.roninbundle"
    export_catalog_bundle(source, _WS, (_SOURCE_REF, _DERIVED_REF), bundle)
    return bundle


def test_catalog_bundle_commit_is_atomic_and_retry_safe(tmp_path: Path) -> None:
    bundle = _export(tmp_path)
    target = _store(tmp_path / "target.sqlite3")

    first = commit_catalog_bundle_import(bundle, target, _WS, now=_NOW)
    assert first.commit.assets_created == 2
    assert first.commit.revisions_created == 2
    assert first.commit.lineage_created == 1
    assert target.get_asset(_WS, _SOURCE) == _assets()[0]
    assert target.get_asset(_WS, _DERIVED) == _assets()[1]
    assert target.get_revision(_WS, _SOURCE_REF) == _revisions()[0]
    assert target.get_revision(_WS, _DERIVED_REF) == _revisions()[1]
    assert target.downstream(_WS, _SOURCE_REF) == (_lineage(),)

    second = commit_catalog_bundle_import(bundle, target, _WS, now=_NOW)
    assert second.commit.assets_created == 0
    assert second.commit.revisions_created == 0
    assert second.commit.lineage_created == 0
    assert all(item.disposition == "noop" for item in second.plan.objects)


def test_catalog_bundle_commit_rejects_planned_collision_without_mutation(
    tmp_path: Path,
) -> None:
    bundle = _export(tmp_path)
    target = _store(tmp_path / "target.sqlite3")
    target.create_asset(
        _WS,
        CatalogAsset(_SOURCE, "table", "Different source"),
        now=_NOW,
    )

    with pytest.raises(CatalogBundleImportConflict, match="different content"):
        commit_catalog_bundle_import(bundle, target, _WS, now=_NOW)
    assert target.get_asset(_WS, _DERIVED) is None
    assert target.get_revision(_WS, _SOURCE_REF) is None


def test_sqlite_catalog_commit_rolls_back_assets_after_late_asset_conflict(
    tmp_path: Path,
) -> None:
    target = _store(tmp_path / "target.sqlite3")
    early = CatalogAsset(AssetId("asset/a-new"), "table", "New")
    late_id = AssetId("asset/z-conflict")
    target.create_asset(
        _WS,
        CatalogAsset(late_id, "table", "Existing"),
        now=_NOW,
    )

    with pytest.raises(CatalogBundleImportConflict, match="different content"):
        target.commit_catalog_import(
            _WS,
            (
                early,
                CatalogAsset(late_id, "table", "Incoming"),
            ),
            (),
            (),
            now=_NOW,
        )
    assert target.get_asset(_WS, early.id) is None
    assert target.get_asset(_WS, late_id) == CatalogAsset(
        late_id,
        "table",
        "Existing",
    )


def test_sqlite_catalog_commit_rolls_back_when_lineage_revision_is_missing(
    tmp_path: Path,
) -> None:
    target = _store(tmp_path / "target.sqlite3")
    source_id = AssetId("asset/a")
    target_id = AssetId("asset/b")
    source_ref = AssetRef(source_id, AssetVersion("1"))
    target_ref = AssetRef(target_id, AssetVersion("1"))
    missing_ref = AssetRef(AssetId("asset/missing"), AssetVersion("1"))
    source_asset = CatalogAsset(source_id, "table", "Source")
    target_asset = CatalogAsset(target_id, "table", "Target")
    source_revision = AssetRevision(source_ref)
    target_revision = AssetRevision(target_ref)
    invalid_edge = LineageEdge(
        source_ref,
        missing_ref,
        operation="transform",
        mode="declared",
    )

    with pytest.raises(CatalogBundleImportConflict, match="missing asset revision"):
        target.commit_catalog_import(
            _WS,
            (source_asset, target_asset),
            (source_revision, target_revision),
            (invalid_edge,),
            now=_NOW,
        )
    assert target.get_asset(_WS, source_id) is None
    assert target.get_asset(_WS, target_id) is None
    assert target.get_revision(_WS, source_ref) is None
