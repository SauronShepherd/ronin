"""SQLite persistence for project-scoped notebook revisions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import cast

from studio_notebook.revisions import (
    NotebookRevision,
    NotebookRevisionConflict,
    NotebookRevisionNotFound,
    NotebookRevisionStore,
    _digest,
    _optional_text,
    _parameters,
)
from studio_notebook.serialization import NotebookDocument

from .sqlite import open_database


class SqliteNotebookRevisionStore(NotebookRevisionStore):
    """Persist immutable notebook revisions in one project namespace."""

    def __init__(self, path: Path, project_id: str) -> None:
        NotebookRevisionStore._validate_id(project_id)
        self._path = path
        self._project_id = project_id
        with closing(open_database(path)) as connection:
            self._migrate(connection)

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS ronin_notebook_revisions ("
            "project_id TEXT NOT NULL, notebook_id TEXT NOT NULL, revision INTEGER NOT NULL,"
            "content_digest TEXT NOT NULL, document_json TEXT NOT NULL,"
            "source_revision TEXT, archived INTEGER NOT NULL, execution_binding TEXT,"
            "evidence_digest TEXT, parameter_schema_json TEXT NOT NULL,"
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "PRIMARY KEY(project_id,notebook_id,revision))"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ronin_notebook_revisions_latest "
            "ON ronin_notebook_revisions(project_id,notebook_id,revision DESC)"
        )

    def _latest_row(self, connection: sqlite3.Connection, notebook_id: str) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            connection.execute(
                "SELECT * FROM ronin_notebook_revisions "
                "WHERE project_id=? AND notebook_id=? ORDER BY revision DESC LIMIT 1",
                (self._project_id, notebook_id),
            ).fetchone(),
        )

    def _latest_rows(self, connection: sqlite3.Connection) -> list[sqlite3.Row]:
        return connection.execute(
            "SELECT r.* FROM ronin_notebook_revisions r "
            "JOIN (SELECT notebook_id, MAX(revision) AS revision "
            "FROM ronin_notebook_revisions WHERE project_id=? GROUP BY notebook_id) latest "
            "ON latest.notebook_id=r.notebook_id AND latest.revision=r.revision "
            "WHERE r.project_id=? ORDER BY r.notebook_id",
            (self._project_id, self._project_id),
        ).fetchall()

    @staticmethod
    def _parameters_from_row(row: sqlite3.Row) -> tuple[tuple[str, str], ...]:
        raw = json.loads(cast(str, row["parameter_schema_json"]))
        if not isinstance(raw, list):
            raise ValueError("stored notebook parameter schema must be an array")
        values: list[tuple[str, str]] = []
        for item in raw:
            if not isinstance(item, Mapping):
                raise ValueError("stored notebook parameter schema entry must be an object")
            name, type_name = item.get("name"), item.get("type")
            if not isinstance(name, str) or not isinstance(type_name, str):
                raise ValueError("stored notebook parameter schema entry is invalid")
            values.append((name, type_name))
        return _parameters(tuple(values))

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> NotebookRevision:
        document_data = json.loads(cast(str, row["document_json"]))
        if not isinstance(document_data, Mapping):
            raise ValueError("stored notebook document must be an object")
        return NotebookRevision(
            notebook_id=cast(str, row["notebook_id"]),
            revision=int(row["revision"]),
            content_digest=cast(str, row["content_digest"]),
            document=NotebookDocument.from_data(document_data),
            source_revision=cast(str | None, row["source_revision"]),
            archived=bool(row["archived"]),
            execution_binding=cast(str | None, row["execution_binding"]),
            evidence_digest=cast(str | None, row["evidence_digest"]),
            parameter_schema=cls._parameters_from_row(row),
        )

    @staticmethod
    def _parameter_json(parameters: tuple[tuple[str, str], ...]) -> str:
        return json.dumps(
            [{"name": name, "type": type_name} for name, type_name in parameters],
            sort_keys=True,
            separators=(",", ":"),
        )

    def _insert(self, connection: sqlite3.Connection, item: NotebookRevision) -> None:
        connection.execute(
            "INSERT INTO ronin_notebook_revisions("
            "project_id,notebook_id,revision,content_digest,document_json,source_revision,"
            "archived,execution_binding,evidence_digest,parameter_schema_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                self._project_id,
                item.notebook_id,
                item.revision,
                item.content_digest,
                item.document.to_json(),
                item.source_revision,
                int(item.archived),
                item.execution_binding,
                item.evidence_digest,
                self._parameter_json(item.parameter_schema),
            ),
        )

    def create(
        self,
        notebook_id: str,
        document: NotebookDocument,
        *,
        source_revision: str | None = None,
        execution_binding: str | None = None,
        parameter_schema: tuple[tuple[str, str], ...] = (),
    ) -> NotebookRevision:
        self._validate_id(notebook_id)
        source_revision = _optional_text(source_revision, "source_revision")
        execution_binding = _optional_text(execution_binding, "execution_binding")
        parameter_schema = _parameters(parameter_schema)
        item = NotebookRevision(
            notebook_id,
            1,
            _digest(document),
            document,
            source_revision,
            False,
            execution_binding,
            None,
            parameter_schema,
        )
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                if self._latest_row(connection, notebook_id) is not None:
                    raise NotebookRevisionConflict(f"notebook already exists: {notebook_id}")
                self._insert(connection, item)
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return item

    def get(self, notebook_id: str) -> NotebookRevision:
        self._validate_id(notebook_id)
        with closing(self._connect()) as connection:
            row = self._latest_row(connection, notebook_id)
        if row is None:
            raise NotebookRevisionNotFound(notebook_id)
        return self._from_row(row)

    def get_revision(self, notebook_id: str, revision: int) -> NotebookRevision:
        self._validate_id(notebook_id)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("revision must be a positive integer")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM ronin_notebook_revisions "
                "WHERE project_id=? AND notebook_id=? AND revision=?",
                (self._project_id, notebook_id, revision),
            ).fetchone()
        if row is None:
            raise NotebookRevisionNotFound(
                f"notebook revision does not exist: {notebook_id}@{revision}"
            )
        return self._from_row(row)

    def list_revisions(self, notebook_id: str) -> tuple[NotebookRevision, ...]:
        self._validate_id(notebook_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM ronin_notebook_revisions "
                "WHERE project_id=? AND notebook_id=? ORDER BY revision",
                (self._project_id, notebook_id),
            ).fetchall()
        if not rows:
            raise NotebookRevisionNotFound(notebook_id)
        return tuple(self._from_row(row) for row in rows)

    def save(
        self,
        notebook_id: str,
        document: NotebookDocument,
        *,
        expected_revision: int,
        source_revision: str | None = None,
        execution_binding: str | None = None,
        evidence_digest: str | None = None,
        parameter_schema: tuple[tuple[str, str], ...] = (),
    ) -> NotebookRevision:
        self._validate_id(notebook_id)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("expected_revision must be a positive integer")
        source_revision = _optional_text(source_revision, "source_revision")
        execution_binding = _optional_text(execution_binding, "execution_binding")
        evidence_digest = _optional_text(evidence_digest, "evidence_digest")
        parameter_schema = _parameters(parameter_schema)
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._latest_row(connection, notebook_id)
                if row is None:
                    raise NotebookRevisionNotFound(notebook_id)
                current = self._from_row(row)
                if current.archived:
                    raise NotebookRevisionConflict("cannot save an archived notebook")
                if current.revision != expected_revision:
                    raise NotebookRevisionConflict(
                        f"stale notebook revision: expected {expected_revision}, "
                        f"current {current.revision}"
                    )
                item = NotebookRevision(
                    notebook_id,
                    current.revision + 1,
                    _digest(document),
                    document,
                    source_revision,
                    False,
                    execution_binding,
                    evidence_digest,
                    parameter_schema,
                )
                self._insert(connection, item)
                connection.execute("COMMIT")
                return item
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def archive(self, notebook_id: str, *, expected_revision: int) -> NotebookRevision:
        self._validate_id(notebook_id)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("expected_revision must be a positive integer")
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._latest_row(connection, notebook_id)
                if row is None:
                    raise NotebookRevisionNotFound(notebook_id)
                current = self._from_row(row)
                if current.revision != expected_revision:
                    raise NotebookRevisionConflict("stale notebook revision")
                item = NotebookRevision(
                    notebook_id,
                    current.revision + 1,
                    current.content_digest,
                    current.document,
                    current.source_revision,
                    True,
                    current.execution_binding,
                    current.evidence_digest,
                    current.parameter_schema,
                )
                self._insert(connection, item)
                connection.execute("COMMIT")
                return item
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def delete(self, notebook_id: str, *, expected_revision: int) -> None:
        self._validate_id(notebook_id)
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise ValueError("expected_revision must be a positive integer")
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._latest_row(connection, notebook_id)
                if row is None:
                    raise NotebookRevisionNotFound(notebook_id)
                current = self._from_row(row)
                if current.revision != expected_revision:
                    raise NotebookRevisionConflict("stale notebook revision")
                connection.execute(
                    "DELETE FROM ronin_notebook_revisions WHERE project_id=? AND notebook_id=?",
                    (self._project_id, notebook_id),
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def list(self, *, include_archived: bool = False) -> tuple[NotebookRevision, ...]:
        with closing(self._connect()) as connection:
            rows = self._latest_rows(connection)
        return tuple(
            self._from_row(row) for row in rows if include_archived or not bool(row["archived"])
        )


__all__ = ("SqliteNotebookRevisionStore",)
