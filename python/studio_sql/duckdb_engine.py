"""Optional DuckDB-backed local SQL reference engine."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import SqlColumn, SqlQueryResult

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DuckDbDependencyError(RuntimeError):
    """Raised when the optional DuckDB dependency is unavailable."""


def _duckdb() -> Any:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - depends on optional installation
        raise DuckDbDependencyError(
            "local SQL support requires the optional Ronin data-plane dependencies"
        ) from exc
    return duckdb


class DuckDbSqlEngine:
    """In-process SQL reference engine over explicitly registered Parquet files."""

    def __init__(self) -> None:
        duckdb = _duckdb()
        self._connection = duckdb.connect(database=":memory:")
        self._closed = False

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQL engine is closed")

    def register_parquet(self, name: str, path: str) -> None:
        self._require_open()
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError("SQL registration name must be a simple identifier")
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("registered Parquet path must be a regular file")
        relation = self._connection.from_parquet(str(resolved))
        relation.create_view(name, replace=True)

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        self._require_open()
        if not sql or sql != sql.strip():
            raise ValueError("SQL text must be non-empty and trimmed")
        if max_rows < 1:
            raise ValueError("max_rows must be positive")

        cursor = self._connection.execute(sql, parameters)
        description = cursor.description or ()
        columns = tuple(SqlColumn(item[0], str(item[1])) for item in description)
        rows = tuple(tuple(row) for row in cursor.fetchmany(max_rows + 1))
        if len(rows) > max_rows:
            raise ValueError("SQL result exceeds max_rows; use a more selective query")
        return SqlQueryResult(columns, rows)

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> DuckDbSqlEngine:
        self._require_open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


__all__ = ("DuckDbDependencyError", "DuckDbSqlEngine")
