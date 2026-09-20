"""SQLite persistence for Data Enginerring pipeline revisions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path

from studio_storage.sqlite import open_database


class SqliteRevisionStore:
    """Owns only Data Enginerring tables and preserves immutable revisions."""

    def __init__(self, path: Path) -> None:
        self._path = path
        connection = open_database(path)
        try:
            self._migrate(connection)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS de_revisions ("
            "project_id TEXT NOT NULL, pipeline_id TEXT NOT NULL, revision INTEGER NOT NULL,"
            "source_digest TEXT NOT NULL, project_artifact_ref TEXT NOT NULL,"
            "pipeline_artifacts_json TEXT NOT NULL, metadata_artifact_ref TEXT NOT NULL,"
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "PRIMARY KEY(project_id,pipeline_id,revision))"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS de_revisions_latest "
            "ON de_revisions(project_id,pipeline_id,revision DESC)"
        )

    def save(
        self,
        *,
        project_id: str,
        pipeline_id: str,
        source_digest: str,
        project_artifact_ref: str,
        pipeline_artifacts: Mapping[str, str],
        metadata_artifact_ref: str,
        expected_revision: int | None = None,
    ) -> int:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(revision),0) AS revision FROM de_revisions "
                "WHERE project_id=? AND pipeline_id=?",
                (project_id, pipeline_id),
            ).fetchone()
            current = int(row["revision"])
            if expected_revision is not None and expected_revision != current:
                raise ValueError(f"stale revision: expected {expected_revision}, current {current}")
            revision = current + 1
            connection.execute(
                "INSERT INTO de_revisions(project_id,pipeline_id,revision,source_digest,"
                "project_artifact_ref,pipeline_artifacts_json,metadata_artifact_ref) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    project_id,
                    pipeline_id,
                    revision,
                    source_digest,
                    project_artifact_ref,
                    json.dumps(dict(sorted(pipeline_artifacts.items())), separators=(",", ":")),
                    metadata_artifact_ref,
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

    def get_latest(self, *, project_id: str, pipeline_id: str) -> dict[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM de_revisions WHERE project_id=? AND pipeline_id=? "
                "ORDER BY revision DESC LIMIT 1",
                (project_id, pipeline_id),
            ).fetchone()
            if row is None:
                return None
            return {
                "project_id": row["project_id"],
                "pipeline_id": row["pipeline_id"],
                "revision": int(row["revision"]),
                "source_digest": row["source_digest"],
                "project_artifact_ref": row["project_artifact_ref"],
                "pipeline_artifacts": json.loads(row["pipeline_artifacts_json"]),
                "metadata_artifact_ref": row["metadata_artifact_ref"],
            }
        finally:
            connection.close()


__all__ = ("SqliteRevisionStore",)
