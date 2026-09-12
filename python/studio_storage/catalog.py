"""Durable governed-asset catalog and lineage persistence for Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import AssetId, AssetRef, AssetRevision, CatalogAsset, LineageEdge, WorkspaceId
from studio_orchestrator import Instant

from .sqlite import open_database
from .workspaces import WorkspaceNotFound, migrate_workspaces

_CATALOG_SCHEMA_VERSION = 1
_CATALOG_MIGRATIONS = {1: "catalog_001.sql"}


class CatalogConflict(RuntimeError):
    """Raised when catalog state conflicts with an attempted mutation."""


class CatalogAssetNotFound(KeyError):
    """Raised when a governed asset is absent."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_catalog(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_workspaces(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS catalog_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM catalog_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _CATALOG_SCHEMA_VERSION:
        raise RuntimeError(
            f"catalog schema {current} is newer than supported {_CATALOG_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _CATALOG_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_CATALOG_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO catalog_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def catalog_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM catalog_schema_migrations").fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SqliteCatalogStore:
    """SQLite reference store for governed assets, revisions, and committed lineage."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_catalog(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def _require_workspace(self, connection: sqlite3.Connection, workspace_id: WorkspaceId) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise CatalogConflict("cannot mutate catalog state in an archived workspace")

    def create_asset(
        self, workspace_id: WorkspaceId, asset: CatalogAsset, *, now: Instant | str
    ) -> CatalogAsset:
        now = Instant(now)
        payload = asset.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT definition_json FROM catalog_assets WHERE workspace_id=? AND asset_id=?",
                (str(workspace_id), str(asset.id)),
            ).fetchone()
            if existing is not None:
                if existing["definition_json"] == payload:
                    connection.execute("COMMIT")
                    return asset
                raise CatalogConflict(f"asset id already exists: {asset.id}")
            connection.execute(
                "INSERT INTO catalog_assets(workspace_id,asset_id,definition_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?)",
                (str(workspace_id), str(asset.id), payload, now, now),
            )
            connection.execute("COMMIT")
            return asset
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def replace_asset(
        self, workspace_id: WorkspaceId, asset: CatalogAsset, *, now: Instant | str
    ) -> CatalogAsset:
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_workspace(connection, workspace_id)
            cursor = connection.execute(
                "UPDATE catalog_assets SET definition_json=?,updated_at=?,row_version=row_version+1 "
                "WHERE workspace_id=? AND asset_id=?",
                (asset.to_json(), now, str(workspace_id), str(asset.id)),
            )
            if cursor.rowcount != 1:
                raise CatalogAssetNotFound(str(asset.id))
            connection.execute("COMMIT")
            return asset
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_asset(self, workspace_id: WorkspaceId, asset_id: AssetId) -> CatalogAsset | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM catalog_assets WHERE workspace_id=? AND asset_id=?",
                (str(workspace_id), str(asset_id)),
            ).fetchone()
            return None if row is None else CatalogAsset.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_assets(self, workspace_id: WorkspaceId) -> tuple[CatalogAsset, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM catalog_assets WHERE workspace_id=? ORDER BY asset_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(CatalogAsset.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def put_revision(
        self, workspace_id: WorkspaceId, revision: AssetRevision, *, now: Instant | str
    ) -> AssetRevision:
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_workspace(connection, workspace_id)
            asset_row = connection.execute(
                "SELECT 1 FROM catalog_assets WHERE workspace_id=? AND asset_id=?",
                (str(workspace_id), str(revision.ref.asset_id)),
            ).fetchone()
            if asset_row is None:
                raise CatalogAssetNotFound(str(revision.ref.asset_id))
            existing = connection.execute(
                "SELECT revision_json FROM catalog_asset_revisions "
                "WHERE workspace_id=? AND asset_id=? AND version=?",
                (
                    str(workspace_id),
                    str(revision.ref.asset_id),
                    str(revision.ref.version),
                ),
            ).fetchone()
            payload = revision.to_json()
            if existing is not None:
                if existing["revision_json"] == payload:
                    connection.execute("COMMIT")
                    return revision
                raise CatalogConflict("asset version already exists with different revision metadata")
            connection.execute(
                "INSERT INTO catalog_asset_revisions(workspace_id,asset_id,version,revision_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(revision.ref.asset_id),
                    str(revision.ref.version),
                    payload,
                    now,
                ),
            )
            connection.execute("COMMIT")
            return revision
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_revision(self, workspace_id: WorkspaceId, ref: AssetRef) -> AssetRevision | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT revision_json FROM catalog_asset_revisions "
                "WHERE workspace_id=? AND asset_id=? AND version=?",
                (str(workspace_id), str(ref.asset_id), str(ref.version)),
            ).fetchone()
            return None if row is None else AssetRevision.from_json(row["revision_json"])
        finally:
            connection.close()

    def put_lineage(
        self, workspace_id: WorkspaceId, edge: LineageEdge, *, now: Instant | str
    ) -> LineageEdge:
        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_workspace(connection, workspace_id)
            for ref in (edge.source, edge.target):
                revision = connection.execute(
                    "SELECT 1 FROM catalog_asset_revisions "
                    "WHERE workspace_id=? AND asset_id=? AND version=?",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                ).fetchone()
                if revision is None:
                    raise CatalogAssetNotFound(f"missing lineage revision: {ref.asset_id}@{ref.version}")
            existing = connection.execute(
                "SELECT edge_json FROM lineage_edges WHERE workspace_id=? AND edge_digest=?",
                (str(workspace_id), edge.digest),
            ).fetchone()
            payload = edge.to_json()
            if existing is not None:
                if existing["edge_json"] == payload:
                    connection.execute("COMMIT")
                    return edge
                raise CatalogConflict("lineage digest collision with different payload")
            connection.execute(
                "INSERT INTO lineage_edges(workspace_id,edge_digest,source_asset_id,source_version,"
                "target_asset_id,target_version,edge_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    edge.digest,
                    str(edge.source.asset_id),
                    str(edge.source.version),
                    str(edge.target.asset_id),
                    str(edge.target.version),
                    payload,
                    now,
                ),
            )
            connection.execute("COMMIT")
            return edge
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def upstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT edge_json FROM lineage_edges WHERE workspace_id=? "
                "AND target_asset_id=? AND target_version=? ORDER BY edge_digest",
                (str(workspace_id), str(ref.asset_id), str(ref.version)),
            ).fetchall()
            return tuple(LineageEdge.from_json(row["edge_json"]) for row in rows)
        finally:
            connection.close()

    def downstream(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[LineageEdge, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT edge_json FROM lineage_edges WHERE workspace_id=? "
                "AND source_asset_id=? AND source_version=? ORDER BY edge_digest",
                (str(workspace_id), str(ref.asset_id), str(ref.version)),
            ).fetchall()
            return tuple(LineageEdge.from_json(row["edge_json"]) for row in rows)
        finally:
            connection.close()
