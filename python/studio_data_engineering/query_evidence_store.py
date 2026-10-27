"""Durable references for Data Engineering QueryFlux evidence artifacts."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from studio_storage import ArtifactRef
from studio_storage.postgres_core import _psycopg
from studio_storage.sqlite import open_database


class SqliteQueryEvidenceReferenceStore:
    """Persist query evidence references in the local composed profile."""

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
            "CREATE TABLE IF NOT EXISTS de_query_evidence_refs ("
            "project_id TEXT NOT NULL, run_id TEXT NOT NULL, attempt_id TEXT NOT NULL,"
            "storage_ref TEXT NOT NULL, digest TEXT NOT NULL,"
            "PRIMARY KEY(project_id,run_id,attempt_id))"
        )

    def record(
        self,
        *,
        project_id: str,
        run_id: str,
        attempt_id: str,
        artifact: ArtifactRef,
    ) -> None:
        _validate_identity(project_id, run_id, attempt_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO de_query_evidence_refs "
                "(project_id,run_id,attempt_id,storage_ref,digest) VALUES (?,?,?,?,?)",
                (project_id, run_id, attempt_id, artifact.storage_ref, artifact.digest),
            )
            row = connection.execute(
                "SELECT storage_ref,digest FROM de_query_evidence_refs "
                "WHERE project_id=? AND run_id=? AND attempt_id=?",
                (project_id, run_id, attempt_id),
            ).fetchone()
            if (
                row is None
                or row["storage_ref"] != artifact.storage_ref
                or row["digest"] != artifact.digest
            ):
                raise ValueError("QueryFlux attempt already has a different evidence artifact")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_evidence_reference(
        self, *, project_id: str, run_id: str, attempt_id: str
    ) -> dict[str, str] | None:
        _validate_identity(project_id, run_id, attempt_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT storage_ref,digest FROM de_query_evidence_refs "
                "WHERE project_id=? AND run_id=? AND attempt_id=?",
                (project_id, run_id, attempt_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return {
            "project_id": project_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "storage_ref": str(row["storage_ref"]),
            "digest": str(row["digest"]),
        }

    def list_evidence_references(
        self, *, max_references: int = 10_000
    ) -> tuple[dict[str, object], ...]:
        if max_references < 1 or max_references > 100_000:
            raise ValueError("QueryFlux evidence reference bound must be between 1 and 100000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT project_id,run_id,attempt_id,storage_ref,digest "
                "FROM de_query_evidence_refs ORDER BY project_id,run_id,attempt_id LIMIT ?",
                (max_references + 1,),
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > max_references:
            raise ValueError("QueryFlux evidence reference inventory exceeded its bound")
        return tuple(dict(row) for row in rows)


class PostgresQueryEvidenceReferenceStore:
    """Persist query evidence references in the shared PostgreSQL profile."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-de-query-evidence") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name
        self.migrate()

    def _connect(self) -> Any:
        psycopg, _dict_row = _psycopg()
        return psycopg.connect(self._dsn, autocommit=False, application_name=self._application_name)

    def migrate(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_de_query_evidence_refs ("
                    "project_id TEXT NOT NULL, run_id TEXT NOT NULL, attempt_id TEXT NOT NULL,"
                    "storage_ref TEXT NOT NULL, digest TEXT NOT NULL,"
                    "PRIMARY KEY(project_id,run_id,attempt_id))"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record(
        self,
        *,
        project_id: str,
        run_id: str,
        attempt_id: str,
        artifact: ArtifactRef,
    ) -> None:
        _validate_identity(project_id, run_id, attempt_id)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_de_query_evidence_refs "
                    "(project_id,run_id,attempt_id,storage_ref,digest) VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (project_id,run_id,attempt_id) DO NOTHING",
                    (project_id, run_id, attempt_id, artifact.storage_ref, artifact.digest),
                )
                cursor.execute(
                    "SELECT storage_ref,digest FROM ronin_de_query_evidence_refs "
                    "WHERE project_id=%s AND run_id=%s AND attempt_id=%s",
                    (project_id, run_id, attempt_id),
                )
                row = cursor.fetchone()
                if row is None or row[0] != artifact.storage_ref or row[1] != artifact.digest:
                    raise ValueError("QueryFlux attempt already has a different evidence artifact")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_evidence_reference(
        self, *, project_id: str, run_id: str, attempt_id: str
    ) -> dict[str, str] | None:
        _validate_identity(project_id, run_id, attempt_id)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT storage_ref,digest FROM ronin_de_query_evidence_refs "
                    "WHERE project_id=%s AND run_id=%s AND attempt_id=%s",
                    (project_id, run_id, attempt_id),
                )
                row = cursor.fetchone()
            connection.commit()
        finally:
            connection.close()
        if row is None:
            return None
        return {
            "project_id": project_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "storage_ref": str(row[0]),
            "digest": str(row[1]),
        }

    def list_evidence_references(
        self, *, max_references: int = 10_000
    ) -> tuple[dict[str, object], ...]:
        if max_references < 1 or max_references > 100_000:
            raise ValueError("QueryFlux evidence reference bound must be between 1 and 100000")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT project_id,run_id,attempt_id,storage_ref,digest "
                    "FROM ronin_de_query_evidence_refs "
                    "ORDER BY project_id,run_id,attempt_id LIMIT %s",
                    (max_references + 1,),
                )
                rows = cursor.fetchall()
            connection.commit()
        finally:
            connection.close()
        if len(rows) > max_references:
            raise ValueError("QueryFlux evidence reference inventory exceeded its bound")
        return tuple(
            {
                "project_id": str(row[0]),
                "run_id": str(row[1]),
                "attempt_id": str(row[2]),
                "storage_ref": str(row[3]),
                "digest": str(row[4]),
            }
            for row in rows
        )


def _validate_identity(project_id: str, run_id: str, attempt_id: str) -> None:
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (project_id, run_id, attempt_id)
    ):
        raise ValueError("project_id, run_id, and attempt_id must be non-empty")


__all__ = (
    "PostgresQueryEvidenceReferenceStore",
    "SqliteQueryEvidenceReferenceStore",
)
