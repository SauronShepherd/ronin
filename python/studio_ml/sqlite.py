"""SQLite adapter for the ML Studio lab and pipeline ports."""
# ruff: noqa: E501, E701, E702

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from studio_core import WorkspaceId
from studio_orchestrator import Instant
from studio_storage.sqlite import open_database

from .domain import Lab, PipelineIR, PipelineNode
from .orchestration import ExecutionSnapshot, ExecutionStore
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
                "CREATE TABLE IF NOT EXISTS ml_studio_executions (run_id TEXT PRIMARY KEY, state TEXT NOT NULL, error TEXT, result_json TEXT)"
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
            from studio_core.canonical_json import decode

            payload = decode(row["pipeline_json"])
            return PipelineIR(
                tuple(
                    PipelineNode(item["id"], item["kind"], tuple(item["depends_on"]))
                    for item in payload["nodes"]
                ),
                tuple(sorted(payload["parameters"].items())),
                payload["schema"],
            )
        finally:
            connection.close()


class SqliteExecutionStore(ExecutionStore):
    """Durable execution lifecycle store; result payload is retained for audit."""

    def __init__(self, path: Path) -> None:
        self._path = path
        connection = open_database(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_executions (run_id TEXT PRIMARY KEY, state TEXT NOT NULL, error TEXT, result_json TEXT)"
            )
        finally:
            connection.close()

    def put(self, snapshot: ExecutionSnapshot) -> None:
        connection = open_database(self._path)
        try:
            payload = snapshot.result.to_payload() if snapshot.result is not None else snapshot.result_payload
            result = None if payload is None else json.dumps(payload, sort_keys=True)
            connection.execute(
                "INSERT OR REPLACE INTO ml_studio_executions(run_id,state,error,result_json) VALUES (?,?,?,?)",
                (snapshot.run_id, snapshot.state, snapshot.error, result),
            )
        finally:
            connection.close()

    def get(self, run_id: str) -> ExecutionSnapshot | None:
        connection = open_database(self._path)
        try:
            row = connection.execute(
                "SELECT run_id,state,error,result_json FROM ml_studio_executions WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            result_payload = json.loads(row["result_json"]) if row["result_json"] else None
            return ExecutionSnapshot(
                row["run_id"], row["state"], error=row["error"], result_payload=result_payload
            )
        finally:
            connection.close()


__all__ = ["SqliteExecutionStore", "SqliteMLLabStore"]
