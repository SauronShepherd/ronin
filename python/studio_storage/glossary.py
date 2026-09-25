"""Durable versioned glossary persistence for Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import GlossaryTerm, GlossaryTermId, WorkspaceId
from studio_orchestrator import Instant

from .sqlite import execute_migration_script, open_database
from .workspaces import WorkspaceNotFound, migrate_workspaces


class GlossaryConflict(RuntimeError):
    pass


class SqliteGlossaryStore:
    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_workspaces(connection, now=migration_now)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS glossary_schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            current = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version),0) AS version FROM glossary_schema_migrations"
                ).fetchone()["version"]
            )
            if current > 1:
                raise RuntimeError("glossary schema is newer than supported")
            if current == 0:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    script = (
                        Path(__file__)
                        .with_name("migrations")
                        .joinpath("glossary_001.sql")
                        .read_text(encoding="utf-8")
                    )
                    execute_migration_script(connection, script)
                    connection.execute(
                        "INSERT INTO glossary_schema_migrations(version,applied_at) VALUES (?,?)",
                        (1, Instant(migration_now)),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def put(
        self, workspace_id: WorkspaceId, term: GlossaryTerm, *, now: Instant | str
    ) -> GlossaryTerm:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            workspace = connection.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
            ).fetchone()
            if workspace is None:
                raise WorkspaceNotFound(str(workspace_id))
            if workspace["archived_at"] is not None:
                raise GlossaryConflict("cannot mutate glossary in an archived workspace")
            payload = term.to_json()
            existing = connection.execute(
                "SELECT term_json FROM glossary_terms "
                "WHERE workspace_id=? AND term_id=? AND version=?",
                (str(workspace_id), str(term.id), term.version),
            ).fetchone()
            if existing is not None:
                if existing["term_json"] == payload:
                    connection.execute("COMMIT")
                    return term
                raise GlossaryConflict(
                    "glossary term version already exists with different content"
                )
            connection.execute(
                "INSERT INTO glossary_terms"
                "(workspace_id,term_id,version,term_json,created_at) VALUES (?,?,?,?,?)",
                (str(workspace_id), str(term.id), term.version, payload, Instant(now)),
            )
            connection.execute("COMMIT")
            return term
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get(
        self, workspace_id: WorkspaceId, term_id: GlossaryTermId, version: str
    ) -> GlossaryTerm | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT term_json FROM glossary_terms "
                "WHERE workspace_id=? AND term_id=? AND version=?",
                (str(workspace_id), str(term_id), version),
            ).fetchone()
            return None if row is None else GlossaryTerm.from_json(row["term_json"])
        finally:
            connection.close()

    def list_versions(
        self, workspace_id: WorkspaceId, term_id: GlossaryTermId
    ) -> tuple[GlossaryTerm, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT term_json FROM glossary_terms "
                "WHERE workspace_id=? AND term_id=? ORDER BY version",
                (str(workspace_id), str(term_id)),
            ).fetchall()
            return tuple(GlossaryTerm.from_json(row["term_json"]) for row in rows)
        finally:
            connection.close()

    def list_all(self, workspace_id: WorkspaceId) -> tuple[GlossaryTerm, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT term_json FROM glossary_terms "
                "WHERE workspace_id=? ORDER BY term_id,version",
                (str(workspace_id),),
            ).fetchall()
            return tuple(GlossaryTerm.from_json(row["term_json"]) for row in rows)
        finally:
            connection.close()

    def list_latest(self, workspace_id: WorkspaceId) -> tuple[GlossaryTerm, ...]:
        """Return exactly one, lexicographically latest version per term."""
        latest: dict[str, GlossaryTerm] = {}
        for term in self.list_all(workspace_id):
            current = latest.get(str(term.id))
            if current is None or term.version > current.version:
                latest[str(term.id)] = term
        return tuple(latest[key] for key in sorted(latest))

    def search(
        self, workspace_id: WorkspaceId, query: str, *, limit: int = 100
    ) -> tuple[GlossaryTerm, ...]:
        if not query.strip():
            raise ValueError("glossary search query must not be empty")
        if not 1 <= limit <= 1000:
            raise ValueError("glossary search limit must be between 1 and 1000")
        needle = query.casefold().strip()
        return tuple(
            term
            for term in self.list_all(workspace_id)
            if needle
            in " ".join((term.name, term.definition, term.owner, *term.references)).casefold()
        )[:limit]
