"""Durable data-contract and quality-result persistence for Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import AssetRef, DataContract, QualityRun, QualityRunId, WorkspaceId
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound, migrate_catalog
from .sqlite import open_database
from .workspaces import WorkspaceNotFound

_QUALITY_SCHEMA_VERSION = 1
_QUALITY_MIGRATIONS = {1: "quality_001.sql"}


class DataContractConflict(RuntimeError):
    """Raised when immutable contract identity conflicts with different content."""


class DataContractNotFound(KeyError):
    """Raised when no contract exists for an asset revision."""


class QualityRunConflict(RuntimeError):
    """Raised when a quality run ID is reused with different evidence."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_quality(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_catalog(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS quality_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM quality_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _QUALITY_SCHEMA_VERSION:
        raise RuntimeError(
            f"quality schema {current} is newer than supported {_QUALITY_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _QUALITY_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_QUALITY_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO quality_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def quality_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM quality_schema_migrations").fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SqliteQualityStore:
    """SQLite reference adapter for contracts and immutable quality-run evidence."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_quality(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def _require_active_workspace(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise DataContractConflict("cannot mutate quality state in an archived workspace")

    def _require_revision(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId, ref: AssetRef
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM catalog_asset_revisions WHERE workspace_id=? AND asset_id=? AND version=?",
            (str(workspace_id), str(ref.asset_id), str(ref.version)),
        ).fetchone()
        if row is None:
            raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")

    def put_contract(
        self, workspace_id: WorkspaceId, contract: DataContract, *, now: Instant | str
    ) -> DataContract:
        now = Instant(now)
        payload = contract.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            self._require_revision(connection, workspace_id, contract.asset)
            existing = connection.execute(
                "SELECT contract_json FROM data_contracts "
                "WHERE workspace_id=? AND asset_id=? AND asset_version=?",
                (
                    str(workspace_id),
                    str(contract.asset.asset_id),
                    str(contract.asset.version),
                ),
            ).fetchone()
            if existing is not None:
                if existing["contract_json"] == payload:
                    connection.execute("COMMIT")
                    return contract
                connection.execute(
                    "UPDATE data_contracts SET contract_json=?,updated_at=?,row_version=row_version+1 "
                    "WHERE workspace_id=? AND asset_id=? AND asset_version=?",
                    (
                        payload,
                        now,
                        str(workspace_id),
                        str(contract.asset.asset_id),
                        str(contract.asset.version),
                    ),
                )
                connection.execute("COMMIT")
                return contract
            connection.execute(
                "INSERT INTO data_contracts(workspace_id,asset_id,asset_version,contract_json,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(contract.asset.asset_id),
                    str(contract.asset.version),
                    payload,
                    now,
                    now,
                ),
            )
            connection.execute("COMMIT")
            return contract
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_contract(self, workspace_id: WorkspaceId, ref: AssetRef) -> DataContract | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT contract_json FROM data_contracts "
                "WHERE workspace_id=? AND asset_id=? AND asset_version=?",
                (str(workspace_id), str(ref.asset_id), str(ref.version)),
            ).fetchone()
            return None if row is None else DataContract.from_json(row["contract_json"])
        finally:
            connection.close()

    def record_run(
        self, workspace_id: WorkspaceId, run: QualityRun, *, now: Instant | str
    ) -> QualityRun:
        now = Instant(now)
        payload = run.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            self._require_revision(connection, workspace_id, run.asset)
            existing = connection.execute(
                "SELECT run_json FROM quality_runs WHERE workspace_id=? AND quality_run_id=?",
                (str(workspace_id), str(run.id)),
            ).fetchone()
            if existing is not None:
                if existing["run_json"] == payload:
                    connection.execute("COMMIT")
                    return run
                raise QualityRunConflict(f"quality run id already exists: {run.id}")
            connection.execute(
                "INSERT INTO quality_runs(workspace_id,quality_run_id,asset_id,asset_version,status,"
                "run_json,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(run.id),
                    str(run.asset.asset_id),
                    str(run.asset.version),
                    run.status,
                    payload,
                    now,
                ),
            )
            connection.execute("COMMIT")
            return run
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: QualityRunId) -> QualityRun | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_json FROM quality_runs WHERE workspace_id=? AND quality_run_id=?",
                (str(workspace_id), str(run_id)),
            ).fetchone()
            return None if row is None else QualityRun.from_json(row["run_json"])
        finally:
            connection.close()

    def list_runs(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[QualityRun, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT run_json FROM quality_runs WHERE workspace_id=? AND asset_id=? "
                "AND asset_version=? ORDER BY created_at,quality_run_id",
                (str(workspace_id), str(ref.asset_id), str(ref.version)),
            ).fetchall()
            return tuple(QualityRun.from_json(row["run_json"]) for row in rows)
        finally:
            connection.close()
