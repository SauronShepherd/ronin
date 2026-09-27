"""PostgreSQL persistence for immutable SDP pipeline revisions."""

# SQL statements are intentionally kept adjacent to their transaction boundary;
# the suffixes passed to _get are private constants, never user input.
# ruff: noqa: E501, S608

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any, cast


class PostgresRevisionDependencyError(RuntimeError):
    """Raised when psycopg is not installed for the PostgreSQL profile."""


def _psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise PostgresRevisionDependencyError(
            "PostgreSQL revisions require psycopg from Ronin server dependencies"
        ) from exc
    return psycopg, dict_row


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ronin_de_revisions (
    project_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    revision BIGINT NOT NULL,
    source_digest TEXT NOT NULL,
    project_artifact_ref TEXT NOT NULL,
    pipeline_artifacts_json TEXT NOT NULL,
    metadata_artifact_ref TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, pipeline_id, revision)
);
CREATE TABLE IF NOT EXISTS ronin_de_pipeline_state (
    project_id TEXT NOT NULL,
    pipeline_id TEXT NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (project_id, pipeline_id)
);
CREATE INDEX IF NOT EXISTS ronin_de_revisions_latest
    ON ronin_de_revisions(project_id, pipeline_id, revision DESC);
"""


class PostgresRevisionStore:
    """Provider-neutral revision store backed by PostgreSQL transactions."""

    def __init__(self, dsn: str, *, application_name: str = "ronin") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name
        self.migrate()

    def _connect(self) -> Any:
        psycopg, dict_row = _psycopg()
        return psycopg.connect(
            self._dsn,
            autocommit=False,
            row_factory=dict_row,
            application_name=self._application_name,
        )

    def migrate(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_SCHEMA)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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
            or not isinstance(ref, str)
            or not ref
            or ref != ref.strip()
            for name, ref in pipeline_artifacts.items()
        ):
            raise ValueError("pipeline artifacts must contain non-empty names and references")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT archived FROM ronin_de_pipeline_state WHERE project_id=%s AND pipeline_id=%s FOR UPDATE",
                    (project_id, pipeline_id),
                )
                state = cursor.fetchone()
                if state is not None and bool(state["archived"]):
                    raise ValueError("cannot save an archived pipeline")
                cursor.execute(
                    "SELECT COALESCE(MAX(revision), 0) AS revision FROM ronin_de_revisions WHERE project_id=%s AND pipeline_id=%s FOR UPDATE",
                    (project_id, pipeline_id),
                )
                current = int(cursor.fetchone()["revision"])
                if expected_revision is not None and expected_revision != current:
                    raise ValueError(
                        f"stale revision: expected {expected_revision}, current {current}"
                    )
                revision = current + 1
                cursor.execute(
                    "INSERT INTO ronin_de_revisions(project_id,pipeline_id,revision,source_digest,project_artifact_ref,pipeline_artifacts_json,metadata_artifact_ref) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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
                cursor.execute(
                    "INSERT INTO ronin_de_pipeline_state(project_id,pipeline_id,archived) VALUES (%s,%s,FALSE) ON CONFLICT(project_id,pipeline_id) DO UPDATE SET archived=FALSE",
                    (project_id, pipeline_id),
                )
            connection.commit()
            return revision
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _record(row: Mapping[str, object]) -> dict[str, object]:
        result = {
            "project_id": row["project_id"],
            "pipeline_id": row["pipeline_id"],
            "revision": int(cast(int | str, row["revision"])),
            "source_digest": row["source_digest"],
            "project_artifact_ref": row["project_artifact_ref"],
            "pipeline_artifacts": json.loads(str(row["pipeline_artifacts_json"])),
            "metadata_artifact_ref": row["metadata_artifact_ref"],
        }
        result["revision_digest"] = sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return result

    def get_latest(self, *, project_id: str, pipeline_id: str) -> dict[str, object] | None:
        return self._get(
            "WHERE project_id=%s AND pipeline_id=%s ORDER BY revision DESC LIMIT 1",
            (project_id, pipeline_id),
        )

    def get_revision(
        self, *, project_id: str, pipeline_id: str, revision: int
    ) -> dict[str, object] | None:
        if revision < 1:
            raise ValueError("pipeline revision must be positive")
        return self._get(
            "WHERE project_id=%s AND pipeline_id=%s AND revision=%s",
            (project_id, pipeline_id, revision),
        )

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

    def _get(self, suffix: str, params: tuple[object, ...]) -> dict[str, object] | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM ronin_de_revisions " + suffix, params)
                row = cursor.fetchone()
            return None if row is None else self._record(row)
        finally:
            connection.close()

    def list_revisions(self, *, project_id: str, pipeline_id: str) -> tuple[dict[str, object], ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_de_revisions WHERE project_id=%s AND pipeline_id=%s ORDER BY revision DESC",
                    (project_id, pipeline_id),
                )
                return tuple(self._record(row) for row in cursor.fetchall())
        finally:
            connection.close()

    def list_pipelines(self, *, project_id: str) -> tuple[str, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT pipeline_id FROM ronin_de_revisions "
                    "WHERE project_id=%s ORDER BY pipeline_id",
                    (project_id,),
                )
                return tuple(str(row["pipeline_id"]) for row in cursor.fetchall())
        finally:
            connection.close()

    def archive(self, *, project_id: str, pipeline_id: str) -> bool:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_de_pipeline_state(project_id,pipeline_id,archived) VALUES (%s,%s,TRUE) ON CONFLICT(project_id,pipeline_id) DO UPDATE SET archived=TRUE WHERE ronin_de_pipeline_state.archived=FALSE",
                    (project_id, pipeline_id),
                )
                changed = cursor.rowcount == 1
            connection.commit()
            return bool(changed)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ("PostgresRevisionDependencyError", "PostgresRevisionStore")
