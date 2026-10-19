"""SQLite adapter for the ML Studio lab and pipeline ports."""
# ruff: noqa: E501, E701, E702

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import WorkspaceId
from studio_orchestrator import Instant
from studio_storage.sqlite import open_database

from .domain import FeatureDefinition, Lab, PipelineIR
from .ports import MLLabStore
from .services import MLLabConflict


class SqliteMLLabStore(MLLabStore):
    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_labs (workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, lab_json TEXT NOT NULL, PRIMARY KEY(workspace_id, lab_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_pipelines (workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, pipeline_json TEXT NOT NULL, PRIMARY KEY(workspace_id, lab_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_features (workspace_id TEXT NOT NULL, feature_id TEXT NOT NULL, version INTEGER NOT NULL, feature_json TEXT NOT NULL, PRIMARY KEY(workspace_id, feature_id, version))"
            )
            connection.execute(
                "INSERT OR IGNORE INTO ml_studio_schema_migrations(version, applied_at) VALUES (1, ?)",
                (str(Instant(migration_now)),),
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        connection = self._connect()
        payload = lab.to_json()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT lab_json FROM ml_studio_labs WHERE workspace_id=? AND lab_id=?",
                (str(workspace_id), lab.id),
            ).fetchone()
            if row is not None and row["lab_json"] != payload:
                raise MLLabConflict(f"lab id already exists: {lab.id}")
            connection.execute(
                "INSERT OR IGNORE INTO ml_studio_labs(workspace_id, lab_id, lab_json) VALUES (?,?,?)",
                (str(workspace_id), lab.id, payload),
            )
            connection.execute("COMMIT")
            return lab
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT lab_json FROM ml_studio_labs WHERE workspace_id=? AND lab_id=?",
                (str(workspace_id), lab_id),
            ).fetchone()
            return None if row is None else Lab.from_json(row["lab_json"])
        finally:
            connection.close()

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT lab_json FROM ml_studio_labs WHERE workspace_id=? ORDER BY lab_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(Lab.from_json(row["lab_json"]) for row in rows)
        finally:
            connection.close()

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO ml_studio_pipelines(workspace_id, lab_id, pipeline_json) VALUES (?,?,?)",
                (str(workspace_id), lab_id, pipeline.to_json()),
            )
            return pipeline
        finally:
            connection.close()

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT pipeline_json FROM ml_studio_pipelines WHERE workspace_id=? AND lab_id=?",
                (str(workspace_id), lab_id),
            ).fetchone()
            if row is None:
                return None
            raw = row["pipeline_json"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                raise ValueError("stored ML pipeline must be JSON text")
            return PipelineIR.from_json(raw)
        finally:
            connection.close()

    def put_feature_definition(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO ml_studio_features(workspace_id,feature_id,version,feature_json) VALUES (?,?,?,?)",
                (str(workspace_id), definition.id, definition.version, definition.to_json()),
            )
            return definition
        finally:
            connection.close()

    def get_feature_definition(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition | None:
        connection = self._connect()
        try:
            if version is None:
                row = connection.execute(
                    "SELECT feature_json FROM ml_studio_features WHERE workspace_id=? AND feature_id=? ORDER BY version DESC LIMIT 1",
                    (str(workspace_id), feature_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT feature_json FROM ml_studio_features WHERE workspace_id=? AND feature_id=? AND version=?",
                    (str(workspace_id), feature_id, version),
                ).fetchone()
            return None if row is None else FeatureDefinition.from_json(row["feature_json"])
        finally:
            connection.close()

    def list_feature_definitions(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]:
        connection = self._connect()
        try:
            query = "SELECT feature_json FROM ml_studio_features WHERE workspace_id=?"
            args: tuple[object, ...] = (str(workspace_id),)
            if feature_id is not None:
                query += " AND feature_id=?"
                args += (feature_id,)
            query += " ORDER BY feature_id,version"
            rows = connection.execute(query, args).fetchall()
            return tuple(FeatureDefinition.from_json(row["feature_json"]) for row in rows)
        finally:
            connection.close()


__all__ = ["SqliteMLLabStore"]
