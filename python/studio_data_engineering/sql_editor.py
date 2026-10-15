"""Durable, provider-neutral SQL editor lifecycle."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from studio_storage.sqlite import open_database


@dataclass(frozen=True, slots=True)
class SqlQueryRevision:
    project_id: str
    query_id: str
    revision: int
    sql: str
    profile: str
    dialect: str
    provider: str

    @property
    def digest(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SqlExecutionRecord:
    execution_id: str
    project_id: str
    query_id: str
    revision: int
    provider: str
    status: str
    row_count: int
    result_digest: str | None = None
    error_code: str | None = None


class SqliteSqlEditorStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        with open_database(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS de_sql_revisions ("
                "project_id TEXT NOT NULL, query_id TEXT NOT NULL, revision INTEGER NOT NULL,"
                "sql_text TEXT NOT NULL, profile TEXT NOT NULL, dialect TEXT NOT NULL,"
                "provider TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                "PRIMARY KEY(project_id,query_id,revision))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS de_sql_history ("
                "execution_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, query_id TEXT NOT NULL,"
                "revision INTEGER NOT NULL, provider TEXT NOT NULL, status TEXT NOT NULL,"
                "row_count INTEGER NOT NULL, result_digest TEXT, error_code TEXT,"
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def save(
        self,
        *,
        project_id: str,
        query_id: str,
        sql: str,
        profile: str = "local",
        dialect: str = "ansi",
        provider: str = "ronin-local-sql",
        expected_revision: int | None = None,
    ) -> SqlQueryRevision:
        if not all(
            value and value == value.strip()
            for value in (project_id, query_id, sql, profile, dialect, provider)
        ):
            raise ValueError("SQL editor identifiers and text must be non-empty and trimmed")
        with open_database(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(revision),0) AS revision FROM de_sql_revisions "
                "WHERE project_id=? AND query_id=?",
                (project_id, query_id),
            ).fetchone()
            current = int(row["revision"])
            if expected_revision is not None and expected_revision != current:
                raise ValueError(
                    f"stale SQL revision: expected {expected_revision}, current {current}"
                )
            revision = current + 1
            connection.execute(
                "INSERT INTO de_sql_revisions(project_id,query_id,revision,sql_text,"
                "profile,dialect,provider) "
                "VALUES (?,?,?,?,?,?,?)",
                (project_id, query_id, revision, sql, profile, dialect, provider),
            )
        return SqlQueryRevision(project_id, query_id, revision, sql, profile, dialect, provider)

    def latest(self, *, project_id: str, query_id: str) -> SqlQueryRevision | None:
        with open_database(self._path) as connection:
            row = connection.execute(
                "SELECT project_id,query_id,revision,sql_text,profile,dialect,provider "
                "FROM de_sql_revisions WHERE project_id=? AND query_id=? "
                "ORDER BY revision DESC LIMIT 1",
                (project_id, query_id),
            ).fetchone()
        if row is None:
            return None
        return SqlQueryRevision(
            row["project_id"],
            row["query_id"],
            int(row["revision"]),
            row["sql_text"],
            row["profile"],
            row["dialect"],
            row["provider"],
        )

    def list_queries(self, *, project_id: str, limit: int = 100) -> tuple[SqlQueryRevision, ...]:
        """List the latest saved revision for each query in stable order."""
        if not project_id or project_id != project_id.strip():
            raise ValueError("SQL project_id must be non-empty and trimmed")
        if limit < 1 or limit > 1000:
            raise ValueError("SQL query list limit must be between 1 and 1000")
        with open_database(self._path) as connection:
            rows = connection.execute(
                "SELECT r.project_id,r.query_id,r.revision,r.sql_text,r.profile,r.dialect,"
                "r.provider "
                "FROM de_sql_revisions r JOIN ("
                "SELECT query_id,MAX(revision) AS revision FROM de_sql_revisions "
                "WHERE project_id=? GROUP BY query_id"
                ") latest ON latest.query_id=r.query_id AND latest.revision=r.revision "
                "WHERE r.project_id=? ORDER BY r.query_id LIMIT ?",
                (project_id, project_id, limit),
            ).fetchall()
        return tuple(
            SqlQueryRevision(
                row["project_id"],
                row["query_id"],
                int(row["revision"]),
                row["sql_text"],
                row["profile"],
                row["dialect"],
                row["provider"],
            )
            for row in rows
        )

    def record_execution(self, record: SqlExecutionRecord) -> SqlExecutionRecord:
        if record.status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported SQL execution status")
        if record.row_count < 0 or record.row_count > 1_000_000:
            raise ValueError("SQL execution row_count is outside the configured bound")
        with open_database(self._path) as connection:
            revision = connection.execute(
                "SELECT provider FROM de_sql_revisions WHERE project_id=? AND query_id=? "
                "AND revision=?",
                (record.project_id, record.query_id, record.revision),
            ).fetchone()
            if revision is None:
                raise ValueError("SQL execution must reference an existing query revision")
            if revision["provider"] != record.provider:
                raise ValueError("SQL execution provider does not match query revision")
            connection.execute(
                "INSERT OR IGNORE INTO de_sql_history(execution_id,project_id,query_id,revision,"
                "provider,status,row_count,result_digest,error_code) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    record.execution_id,
                    record.project_id,
                    record.query_id,
                    record.revision,
                    record.provider,
                    record.status,
                    record.row_count,
                    record.result_digest,
                    record.error_code,
                ),
            )
        return record

    def history(
        self, *, project_id: str, query_id: str, limit: int = 100
    ) -> tuple[SqlExecutionRecord, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("SQL history limit must be between 1 and 1000")
        with open_database(self._path) as connection:
            rows = connection.execute(
                "SELECT execution_id,project_id,query_id,revision,provider,status,row_count,"
                "result_digest,error_code FROM de_sql_history WHERE project_id=? AND query_id=? "
                "ORDER BY created_at DESC,execution_id DESC LIMIT ?",
                (project_id, query_id, limit),
            ).fetchall()
        return tuple(
            SqlExecutionRecord(
                row["execution_id"],
                row["project_id"],
                row["query_id"],
                int(row["revision"]),
                row["provider"],
                row["status"],
                int(row["row_count"]),
                row["result_digest"],
                row["error_code"],
            )
            for row in rows
        )


def export_sql_rows(
    columns: tuple[str, ...],
    rows: tuple[tuple[object, ...], ...],
    *,
    max_rows: int = 10_000,
    max_bytes: int = 5_000_000,
) -> str:
    """Export bounded SQL results as RFC 4180-compatible CSV."""

    if not columns or len(set(columns)) != len(columns):
        raise ValueError("SQL export columns must be non-empty and unique")
    if max_rows < 1 or max_rows > 100_000 or max_bytes < 1:
        raise ValueError("SQL export bounds are invalid")
    if len(rows) > max_rows:
        raise ValueError("SQL export exceeds max_rows")
    if any(len(row) != len(columns) for row in rows):
        raise ValueError("SQL export row width must match columns")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
        if len(output.getvalue().encode()) > max_bytes:
            raise ValueError("SQL export exceeds max_bytes")
    return output.getvalue()


__all__ = (
    "SqlExecutionRecord",
    "SqlQueryRevision",
    "SqliteSqlEditorStore",
    "export_sql_rows",
)
