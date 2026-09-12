"""Durable ontology-definition persistence for Public v1."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import OntologyDefinition, OntologyId, WorkspaceId
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound, migrate_catalog
from .sqlite import open_database
from .workspaces import WorkspaceNotFound

_ONTOLOGY_SCHEMA_VERSION = 1
_ONTOLOGY_MIGRATIONS = {1: "ontology_001.sql"}


class OntologyConflict(RuntimeError):
    """Raised when an immutable ontology version conflicts with different content."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_ontology(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_catalog(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS ontology_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM ontology_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _ONTOLOGY_SCHEMA_VERSION:
        raise RuntimeError(
            f"ontology schema {current} is newer than supported {_ONTOLOGY_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _ONTOLOGY_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_ONTOLOGY_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO ontology_schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def ontology_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM ontology_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SqliteOntologyStore:
    """SQLite reference adapter for immutable ontology schema versions."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_ontology(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def put(
        self,
        workspace_id: WorkspaceId,
        ontology: OntologyDefinition,
        *,
        now: Instant | str,
    ) -> OntologyDefinition:
        now = Instant(now)
        payload = ontology.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            workspace = connection.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
            ).fetchone()
            if workspace is None:
                raise WorkspaceNotFound(str(workspace_id))
            if workspace["archived_at"] is not None:
                raise OntologyConflict("cannot mutate ontology state in an archived workspace")
            for ref in ontology.asset_refs():
                revision = connection.execute(
                    "SELECT 1 FROM catalog_asset_revisions WHERE workspace_id=? "
                    "AND asset_id=? AND version=?",
                    (str(workspace_id), str(ref.asset_id), str(ref.version)),
                ).fetchone()
                if revision is None:
                    raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")
            existing = connection.execute(
                "SELECT definition_json FROM ontologies WHERE workspace_id=? "
                "AND ontology_id=? AND version=?",
                (str(workspace_id), str(ontology.id), ontology.version),
            ).fetchone()
            if existing is not None:
                if existing["definition_json"] == payload:
                    connection.execute("COMMIT")
                    return ontology
                raise OntologyConflict(
                    f"ontology version already exists with different content: "
                    f"{ontology.id}@{ontology.version}"
                )
            connection.execute(
                "INSERT INTO ontologies(workspace_id,ontology_id,version,definition_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (str(workspace_id), str(ontology.id), ontology.version, payload, now),
            )
            connection.execute("COMMIT")
            return ontology
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId, version: str
    ) -> OntologyDefinition | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT definition_json FROM ontologies WHERE workspace_id=? "
                "AND ontology_id=? AND version=?",
                (str(workspace_id), str(ontology_id), version),
            ).fetchone()
            return None if row is None else OntologyDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_versions(
        self, workspace_id: WorkspaceId, ontology_id: OntologyId
    ) -> tuple[OntologyDefinition, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT definition_json FROM ontologies WHERE workspace_id=? AND ontology_id=? "
                "ORDER BY version",
                (str(workspace_id), str(ontology_id)),
            ).fetchall()
            return tuple(OntologyDefinition.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()
