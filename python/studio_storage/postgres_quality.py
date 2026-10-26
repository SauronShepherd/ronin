"""PostgreSQL persistence for versioned data contracts and quality evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from studio_core import AssetRef, DataContract, QualityRun, QualityRunId, WorkspaceId
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound
from .quality import QualityRunConflict

_SCHEMA_VERSION = 1
_SCHEMA = """
CREATE TABLE ronin_data_contracts (
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, asset_id, asset_version),
    FOREIGN KEY (workspace_id, asset_id, asset_version)
        REFERENCES ronin_catalog_revisions(workspace_id, asset_id, version) ON DELETE CASCADE
);
CREATE TABLE ronin_quality_runs (
    workspace_id TEXT NOT NULL,
    quality_run_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed','failed','error','unknown')),
    run_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, quality_run_id),
    FOREIGN KEY (workspace_id, asset_id, asset_version)
        REFERENCES ronin_catalog_revisions(workspace_id, asset_id, version) ON DELETE CASCADE
);
CREATE INDEX ronin_quality_runs_asset_idx
    ON ronin_quality_runs(workspace_id, asset_id, asset_version, created_at, quality_run_id);
CREATE INDEX ronin_quality_runs_status_idx
    ON ronin_quality_runs(workspace_id, status, created_at, quality_run_id);
"""


class PostgresQualityStore:
    """Quality store backed by a shared PostgreSQL metadata connection provider."""

    def __init__(self, metadata_store: object) -> None:
        connect = getattr(metadata_store, "_connect", None)
        require_workspace = getattr(metadata_store, "_require_active_workspace", None)
        if not callable(connect) or not callable(require_workspace):
            raise TypeError(
                "metadata_store must provide PostgreSQL connections and workspace checks"
            )
        self._metadata: Any = metadata_store
        self._migrate()

    def _connect(self) -> Any:
        return self._metadata._connect()

    def _require_active_workspace(self, cursor: Any, workspace_id: WorkspaceId) -> None:
        self._metadata._require_active_workspace(cursor, workspace_id)

    def _migrate(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("ronin:quality",))
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_quality_schema_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                cursor.execute(
                    "SELECT COALESCE(MAX(version),0) AS version "
                    "FROM ronin_quality_schema_migrations"
                )
                current = int(cursor.fetchone()["version"])
                if current > _SCHEMA_VERSION:
                    raise RuntimeError(
                        f"PostgreSQL quality schema {current} is newer than supported "
                        f"{_SCHEMA_VERSION}"
                    )
                if current == 0:
                    cursor.execute(_SCHEMA)
                    cursor.execute(
                        "INSERT INTO ronin_quality_schema_migrations(version,applied_at) "
                        "VALUES (%s,%s)",
                        (
                            1,
                            datetime.now(UTC)
                            .isoformat(timespec="microseconds")
                            .replace("+00:00", "Z"),
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _require_revision(self, cursor: Any, workspace_id: WorkspaceId, ref: AssetRef) -> None:
        cursor.execute(
            "SELECT 1 FROM ronin_catalog_revisions "
            "WHERE workspace_id=%s AND asset_id=%s AND version=%s",
            (str(workspace_id), str(ref.asset_id), str(ref.version)),
        )
        if cursor.fetchone() is None:
            raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")

    def put_contract(
        self, workspace_id: WorkspaceId, contract: DataContract, *, now: Instant | str
    ) -> DataContract:
        return self.put_contracts(workspace_id, (contract,), now=now)[0]

    def put_contracts(
        self,
        workspace_id: WorkspaceId,
        contracts: tuple[DataContract, ...],
        *,
        now: Instant | str,
    ) -> tuple[DataContract, ...]:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                for contract in contracts:
                    self._require_revision(cursor, workspace_id, contract.asset)
                    payload = contract.to_json()
                    cursor.execute(
                        "INSERT INTO ronin_data_contracts("
                        "workspace_id,asset_id,asset_version,contract_json,created_at,updated_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT(workspace_id,asset_id,asset_version) DO UPDATE SET "
                        "contract_json=EXCLUDED.contract_json,updated_at=EXCLUDED.updated_at, "
                        "row_version=ronin_data_contracts.row_version+1 "
                        "WHERE ronin_data_contracts.contract_json<>EXCLUDED.contract_json",
                        (
                            str(workspace_id),
                            str(contract.asset.asset_id),
                            str(contract.asset.version),
                            payload,
                            str(current),
                            str(current),
                        ),
                    )
            connection.commit()
            return contracts
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_contract(self, workspace_id: WorkspaceId, ref: AssetRef) -> DataContract | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT contract_json FROM ronin_data_contracts "
                    "WHERE workspace_id=%s AND asset_id=%s AND asset_version=%s",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                )
                row = cursor.fetchone()
            return None if row is None else DataContract.from_json(row["contract_json"])
        finally:
            connection.close()

    def list_contracts(self, workspace_id: WorkspaceId) -> tuple[DataContract, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT contract_json FROM ronin_data_contracts WHERE workspace_id=%s "
                    "ORDER BY asset_id,asset_version",
                    (str(workspace_id),),
                )
                rows = cursor.fetchall()
            return tuple(DataContract.from_json(row["contract_json"]) for row in rows)
        finally:
            connection.close()

    def record_run(
        self, workspace_id: WorkspaceId, run: QualityRun, *, now: Instant | str
    ) -> QualityRun:
        current = Instant(now)
        payload = run.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                self._require_revision(cursor, workspace_id, run.asset)
                cursor.execute(
                    "INSERT INTO ronin_quality_runs("
                    "workspace_id,quality_run_id,asset_id,asset_version,status,"
                    "run_json,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(workspace_id,quality_run_id) DO NOTHING",
                    (
                        str(workspace_id),
                        str(run.id),
                        str(run.asset.asset_id),
                        str(run.asset.version),
                        run.status,
                        payload,
                        str(current),
                    ),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        "SELECT run_json FROM ronin_quality_runs "
                        "WHERE workspace_id=%s AND quality_run_id=%s",
                        (str(workspace_id), str(run.id)),
                    )
                    existing = cursor.fetchone()
                    if existing is None or existing["run_json"] != payload:
                        raise QualityRunConflict(f"quality run id already exists: {run.id}")
            connection.commit()
            return run
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: QualityRunId) -> QualityRun | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_json FROM ronin_quality_runs "
                    "WHERE workspace_id=%s AND quality_run_id=%s",
                    (str(workspace_id), str(run_id)),
                )
                row = cursor.fetchone()
            return None if row is None else QualityRun.from_json(row["run_json"])
        finally:
            connection.close()

    def get_run_created_at(self, workspace_id: WorkspaceId, run_id: QualityRunId) -> Instant | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT created_at FROM ronin_quality_runs "
                    "WHERE workspace_id=%s AND quality_run_id=%s",
                    (str(workspace_id), str(run_id)),
                )
                row = cursor.fetchone()
            return None if row is None else Instant(row["created_at"])
        finally:
            connection.close()

    def list_runs(self, workspace_id: WorkspaceId, ref: AssetRef) -> tuple[QualityRun, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_json FROM ronin_quality_runs WHERE workspace_id=%s "
                    "AND asset_id=%s AND asset_version=%s ORDER BY created_at,quality_run_id",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                )
                rows = cursor.fetchall()
            return tuple(QualityRun.from_json(row["run_json"]) for row in rows)
        finally:
            connection.close()


__all__ = ("PostgresQualityStore",)
