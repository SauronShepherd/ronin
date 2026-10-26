from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    OwnershipMetadata,
    SensitivityMetadata,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage import PostgresMetadataStore
from studio_storage.catalog import CatalogAssetNotFound, CatalogConflict

_DSN = os.environ.get("RONIN_TEST_POSTGRES_DSN")
if not _DSN:
    pytest.skip("RONIN_TEST_POSTGRES_DSN is not configured", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")

_NOW = Instant("2026-10-24T00:00:00.000000Z")


def _workspace() -> Workspace:
    suffix = uuid4().hex
    return Workspace(WorkspaceId(f"catalog-test-{suffix}"), f"Catalog Test {suffix}")


def _cleanup(workspace_id: WorkspaceId) -> None:
    with psycopg.connect(_DSN, autocommit=True) as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM ronin_workspaces WHERE workspace_id=%s", (workspace_id.value,))


def test_postgres_catalog_assets_governance_revisions_and_lineage() -> None:
    store = PostgresMetadataStore(_DSN, application_name="ronin-postgres-catalog-test")
    workspace = _workspace()
    store.create_workspace(workspace, now=_NOW)
    source = CatalogAsset(AssetId("source-table"), "table", "Source Orders", tags=("sales",))
    target = CatalogAsset(AssetId("target-table"), "table", "Curated Orders")

    try:
        assert store.create_asset(workspace.id, source, now=_NOW) == source
        assert store.create_asset(workspace.id, source, now=_NOW) == source
        assert store.create_asset(workspace.id, target, now=_NOW) == target
        with pytest.raises(CatalogConflict):
            store.create_asset(
                workspace.id,
                CatalogAsset(AssetId("source-table"), "table", "Conflicting Orders"),
                now=_NOW,
            )
        assert store.list_assets(workspace.id, limit=2) == (source, target)
        with pytest.raises(ValueError, match="catalog asset inventory exceeded"):
            store.list_assets(workspace.id, limit=1)
        first_page = store.list_assets_page(workspace.id, limit=1)
        assert first_page.items == (source,)
        assert first_page.next_cursor is not None
        second_page = store.list_assets_page(workspace.id, limit=1, cursor=first_page.next_cursor)
        assert second_page.items == (target,)
        assert second_page.next_cursor is None
        assert store.search_assets(workspace.id, "sales") == (source,)
        searched_page = store.search_assets_page(workspace.id, "SALES", limit=1)
        assert searched_page.items == (source,)
        assert searched_page.next_cursor is None

        source_revision = AssetRevision(AssetRef(source.id, AssetVersion("1")), schema_digest="s1")
        target_revision = AssetRevision(AssetRef(target.id, AssetVersion("1")), schema_digest="t1")
        assert store.put_revision(workspace.id, source_revision, now=_NOW) == source_revision
        assert store.put_revision(workspace.id, target_revision, now=_NOW) == target_revision
        assert store.get_revision(workspace.id, target_revision.ref) == target_revision
        assert store.list_revisions(workspace.id, target.id) == (target_revision,)

        sensitivity_v1 = SensitivityMetadata(1, explicit=("internal",))
        sensitivity_v2 = SensitivityMetadata(
            2,
            explicit=("confidential",),
            inherited=("internal",),
            inherited_from=("source-table@1",),
        )
        assert (
            store.put_sensitivity(workspace.id, target.id, sensitivity_v1, now=_NOW)
            == sensitivity_v1
        )
        assert (
            store.put_sensitivity(workspace.id, target.id, sensitivity_v1, now=_NOW)
            == sensitivity_v1
        )
        assert (
            store.put_sensitivity(workspace.id, target.id, sensitivity_v2, now=_NOW)
            == sensitivity_v2
        )
        assert store.get_sensitivity(workspace.id, target.id) == sensitivity_v2
        assert store.get_sensitivity(workspace.id, target.id, version=1) == sensitivity_v1
        assert store.list_sensitivity_versions(workspace.id, target.id) == (
            sensitivity_v1,
            sensitivity_v2,
        )
        with pytest.raises(CatalogConflict, match="sensitivity version"):
            store.put_sensitivity(
                workspace.id, target.id, SensitivityMetadata(1, explicit=("restricted",)), now=_NOW
            )

        ownership_v1 = OwnershipMetadata(1, "group/data", ("user/steward",), "sales")
        ownership_v2 = OwnershipMetadata(2, "group/analytics", ("user/steward",), "sales")
        assert store.put_ownership(workspace.id, target.id, ownership_v1, now=_NOW) == ownership_v1
        assert store.put_ownership(workspace.id, target.id, ownership_v2, now=_NOW) == ownership_v2
        assert store.get_ownership(workspace.id, target.id) == ownership_v2
        assert store.get_ownership(workspace.id, target.id, version=1) == ownership_v1
        assert store.list_ownership_versions(workspace.id, target.id) == (
            ownership_v1,
            ownership_v2,
        )
        with pytest.raises(CatalogConflict, match="ownership version"):
            store.put_ownership(
                workspace.id, target.id, OwnershipMetadata(1, "group/conflict"), now=_NOW
            )
        with pytest.raises(CatalogAssetNotFound):
            store.put_ownership(
                workspace.id, AssetId("missing"), OwnershipMetadata(1, "group/data"), now=_NOW
            )

        edge = LineageEdge(source_revision.ref, target_revision.ref, "transform", "declared")
        assert store.put_lineage(workspace.id, edge, now=_NOW) == edge
        assert store.put_lineage(workspace.id, edge, now=_NOW) == edge
        assert store.list_lineage(workspace.id) == (edge,)
        assert store.upstream(workspace.id, target_revision.ref) == (edge,)
        assert store.downstream(workspace.id, source_revision.ref) == (edge,)
        for invalid in (0, 10_001):
            with pytest.raises(ValueError, match="lineage limit"):
                store.list_lineage(workspace.id, limit=invalid)
    finally:
        _cleanup(workspace.id)
