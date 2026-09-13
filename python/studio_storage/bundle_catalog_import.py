"""Atomic SQLite commit boundary for native catalog Bundle imports."""

from __future__ import annotations

from pathlib import Path

from studio_core import AssetRevision, CatalogAsset, LineageEdge, WorkspaceId
from studio_orchestrator import Instant

from .bundle_catalog_import_port import (
    CatalogBundleImportCommit,
    CatalogBundleImportConflict,
)
from .catalog import SqliteCatalogStore, migrate_catalog
from .sqlite import open_database
from .workspaces import SqliteWorkspaceStore


class SqliteCatalogBundleImportStore(SqliteWorkspaceStore, SqliteCatalogStore):
    """SQLite metadata adapter for one-transaction catalog subgraph import."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        SqliteWorkspaceStore.__init__(self, path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_catalog(connection, now=migration_now)
        finally:
            connection.close()

    def commit_catalog_import(
        self,
        workspace_id: WorkspaceId,
        assets: tuple[CatalogAsset, ...],
        revisions: tuple[AssetRevision, ...],
        lineage: tuple[LineageEdge, ...],
        *,
        now: Instant | str,
    ) -> CatalogBundleImportCommit:
        """Create/exact-noop one catalog subgraph atomically."""

        asset_ids = [item.id for item in assets]
        revision_refs = [item.ref for item in revisions]
        lineage_digests = [item.digest for item in lineage]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("catalog import assets must have unique ids")
        if len(revision_refs) != len(set(revision_refs)):
            raise ValueError("catalog import revisions must have unique refs")
        if len(lineage_digests) != len(set(lineage_digests)):
            raise ValueError("catalog import lineage edges must have unique digests")

        current = Instant(now)
        database = self._connect()
        try:
            database.execute("BEGIN IMMEDIATE")
            workspace = database.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?",
                (str(workspace_id),),
            ).fetchone()
            if workspace is None:
                raise CatalogBundleImportConflict("target workspace does not exist")
            if workspace["archived_at"] is not None:
                raise CatalogBundleImportConflict("target workspace is archived")

            assets_created = 0
            for asset in sorted(assets, key=lambda item: str(item.id)):
                payload = asset.to_json()
                existing = database.execute(
                    "SELECT definition_json FROM catalog_assets "
                    "WHERE workspace_id=? AND asset_id=?",
                    (str(workspace_id), str(asset.id)),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO catalog_assets("
                        "workspace_id,asset_id,definition_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?)",
                        (str(workspace_id), str(asset.id), payload, current, current),
                    )
                    assets_created += 1
                elif existing["definition_json"] != payload:
                    raise CatalogBundleImportConflict(
                        f"catalog asset id already exists with different content: {asset.id}"
                    )

            revisions_created = 0
            for revision in sorted(revisions, key=lambda item: item.ref):
                asset = database.execute(
                    "SELECT 1 FROM catalog_assets WHERE workspace_id=? AND asset_id=?",
                    (str(workspace_id), str(revision.ref.asset_id)),
                ).fetchone()
                if asset is None:
                    raise CatalogBundleImportConflict(
                        f"catalog revision references missing asset: {revision.ref.asset_id}"
                    )
                payload = revision.to_json()
                existing = database.execute(
                    "SELECT revision_json FROM catalog_asset_revisions "
                    "WHERE workspace_id=? AND asset_id=? AND version=?",
                    (
                        str(workspace_id),
                        str(revision.ref.asset_id),
                        str(revision.ref.version),
                    ),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO catalog_asset_revisions("
                        "workspace_id,asset_id,version,revision_json,created_at) "
                        "VALUES (?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(revision.ref.asset_id),
                            str(revision.ref.version),
                            payload,
                            current,
                        ),
                    )
                    revisions_created += 1
                elif existing["revision_json"] != payload:
                    raise CatalogBundleImportConflict(
                        "catalog asset version already exists with different revision metadata"
                    )

            lineage_created = 0
            for edge in sorted(lineage, key=lambda item: item.digest):
                for ref in (edge.source, edge.target):
                    revision = database.execute(
                        "SELECT 1 FROM catalog_asset_revisions "
                        "WHERE workspace_id=? AND asset_id=? AND version=?",
                        (
                            str(workspace_id),
                            str(ref.asset_id),
                            str(ref.version),
                        ),
                    ).fetchone()
                    if revision is None:
                        raise CatalogBundleImportConflict(
                            "catalog lineage references missing asset revision"
                        )
                payload = edge.to_json()
                existing = database.execute(
                    "SELECT edge_json FROM lineage_edges "
                    "WHERE workspace_id=? AND edge_digest=?",
                    (str(workspace_id), edge.digest),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO lineage_edges("
                        "workspace_id,edge_digest,source_asset_id,source_version,"
                        "target_asset_id,target_version,edge_json,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (
                            str(workspace_id),
                            edge.digest,
                            str(edge.source.asset_id),
                            str(edge.source.version),
                            str(edge.target.asset_id),
                            str(edge.target.version),
                            payload,
                            current,
                        ),
                    )
                    lineage_created += 1
                elif existing["edge_json"] != payload:
                    raise CatalogBundleImportConflict(
                        "catalog lineage digest exists with different edge content"
                    )

            database.execute("COMMIT")
            return CatalogBundleImportCommit(
                assets_created,
                revisions_created,
                lineage_created,
            )
        except Exception:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
        finally:
            database.close()


__all__ = ("SqliteCatalogBundleImportStore",)
