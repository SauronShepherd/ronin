"""SQLite persistence for Data Enginerring pipeline revisions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from hashlib import sha256
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
        connection.execute(
            "CREATE TABLE IF NOT EXISTS de_pipeline_state ("
            "project_id TEXT NOT NULL, pipeline_id TEXT NOT NULL, archived INTEGER NOT NULL,"
            "PRIMARY KEY(project_id,pipeline_id))"
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
        values = (
            project_id,
            pipeline_id,
            source_digest,
            project_artifact_ref,
            metadata_artifact_ref,
        )
        if any(
            not isinstance(value, str) or not value or value != value.strip() for value in values
        ):
            raise ValueError("pipeline revision identity and artifact references must be non-empty")
        if any(
            not isinstance(name, str)
            or not name
            or name != name.strip()
            or not isinstance(reference, str)
            or not reference
            or reference != reference.strip()
            for name, reference in pipeline_artifacts.items()
        ):
            raise ValueError("pipeline artifacts must contain non-empty names and references")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute(
                "SELECT archived FROM de_pipeline_state WHERE project_id=? AND pipeline_id=?",
                (project_id, pipeline_id),
            ).fetchone()
            if state is not None and bool(state["archived"]):
                raise ValueError("cannot save an archived pipeline")
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
            connection.execute(
                "INSERT INTO de_pipeline_state(project_id,pipeline_id,archived) VALUES (?,?,0) "
                "ON CONFLICT(project_id,pipeline_id) DO UPDATE SET archived=0",
                (project_id, pipeline_id),
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
            result = {
                "project_id": row["project_id"],
                "pipeline_id": row["pipeline_id"],
                "revision": int(row["revision"]),
                "source_digest": row["source_digest"],
                "project_artifact_ref": row["project_artifact_ref"],
                "pipeline_artifacts": json.loads(row["pipeline_artifacts_json"]),
                "metadata_artifact_ref": row["metadata_artifact_ref"],
            }
            result["revision_digest"] = self._revision_digest(result)
            return result
        finally:
            connection.close()

    def get_revision(
        self, *, project_id: str, pipeline_id: str, revision: int
    ) -> dict[str, object] | None:
        if revision < 1:
            raise ValueError("pipeline revision must be positive")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM de_revisions WHERE project_id=? AND pipeline_id=? AND revision=?",
                (project_id, pipeline_id, revision),
            ).fetchone()
        if row is None:
            return None
        result = {
            "project_id": row["project_id"],
            "pipeline_id": row["pipeline_id"],
            "revision": int(row["revision"]),
            "source_digest": row["source_digest"],
            "project_artifact_ref": row["project_artifact_ref"],
            "pipeline_artifacts": json.loads(row["pipeline_artifacts_json"]),
            "metadata_artifact_ref": row["metadata_artifact_ref"],
        }
        result["revision_digest"] = self._revision_digest(result)
        return result

    @staticmethod
    def _revision_digest(record: Mapping[str, object]) -> str:
        payload = json.dumps(
            {
                "project_id": record["project_id"],
                "pipeline_id": record["pipeline_id"],
                "revision": record["revision"],
                "source_digest": record["source_digest"],
                "project_artifact_ref": record["project_artifact_ref"],
                "pipeline_artifacts": dict(sorted(record["pipeline_artifacts"].items())),
                "metadata_artifact_ref": record["metadata_artifact_ref"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return sha256(payload).hexdigest()

    def list_revisions(self, *, project_id: str, pipeline_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            revisions = connection.execute(
                "SELECT revision FROM de_revisions WHERE project_id=? AND pipeline_id=? "
                "ORDER BY revision DESC",
                (project_id, pipeline_id),
            ).fetchall()
        return tuple(
            self.get_revision(project_id=project_id, pipeline_id=pipeline_id, revision=int(row[0]))
            for row in revisions
        )

    def list_pipelines(self, *, project_id: str) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT pipeline_id FROM de_revisions "
                "WHERE project_id=? ORDER BY pipeline_id",
                (project_id,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def compare(
        self, *, project_id: str, pipeline_id: str, left_revision: int, right_revision: int
    ) -> dict[str, object]:
        left = self.get_revision(
            project_id=project_id, pipeline_id=pipeline_id, revision=left_revision
        )
        right = self.get_revision(
            project_id=project_id, pipeline_id=pipeline_id, revision=right_revision
        )
        if left is None or right is None:
            raise KeyError("pipeline revision not found")
        return {
            "left_revision": left_revision,
            "right_revision": right_revision,
            "source_changed": left["source_digest"] != right["source_digest"],
            "project_artifact_changed": left["project_artifact_ref"]
            != right["project_artifact_ref"],
            "pipeline_artifacts_changed": left["pipeline_artifacts"] != right["pipeline_artifacts"],
            "metadata_changed": left["metadata_artifact_ref"] != right["metadata_artifact_ref"],
        }

    def archive(self, *, project_id: str, pipeline_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO de_pipeline_state(project_id,pipeline_id,archived) VALUES (?,?,1) "
                "ON CONFLICT(project_id,pipeline_id) DO UPDATE SET archived=1 "
                "WHERE archived=0",
                (project_id, pipeline_id),
            )
        return cursor.rowcount == 1

    def is_archived(self, *, project_id: str, pipeline_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT archived FROM de_pipeline_state WHERE project_id=? AND pipeline_id=?",
                (project_id, pipeline_id),
            ).fetchone()
        return row is not None and bool(row["archived"])


__all__ = ("SqliteRevisionStore",)
