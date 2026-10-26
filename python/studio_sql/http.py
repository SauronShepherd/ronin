"""Provider-neutral application adapter for the bounded SQL service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .contracts import SqlQueryResult, validate_read_only_select
from .wire import sql_wire_value


class SqlQueryEngine(Protocol):
    def execute(
        self,
        project_id: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult: ...


class SqlHTTPAdapter:
    """Validate a public SQL request and return a stable JSON-compatible payload."""

    def __init__(self, engine: SqlQueryEngine) -> None:
        self._engine = engine

    def close(self) -> None:
        """Close an owned engine when the hosting HTTP server shuts down."""
        close = getattr(self._engine, "close", None)
        if callable(close):
            close()

    def query(self, project_id: str, body: object) -> dict[str, object]:
        if not project_id or project_id != project_id.strip():
            raise ValueError("SQL project_id must be non-empty and trimmed")
        if not isinstance(body, Mapping):
            raise ValueError("SQL query body must be an object")
        sql = body.get("sql")
        if not isinstance(sql, str):
            raise ValueError("SQL query body requires non-empty sql")
        validate_read_only_select(sql)
        max_rows = body.get("max_rows", 10_000)
        if (
            not isinstance(max_rows, int)
            or isinstance(max_rows, bool)
            or not 1 <= max_rows <= 10_000
        ):
            raise ValueError("SQL max_rows must be between 1 and 10000")
        raw_parameters = body.get("parameters", [])
        if not isinstance(raw_parameters, list):
            raise ValueError("SQL parameters must be an array")
        result = self._engine.execute(project_id, sql, tuple(raw_parameters), max_rows=max_rows)
        return {
            "columns": [
                {"name": column.name, "type_name": column.type_name} for column in result.columns
            ],
            "rows": [[sql_wire_value(value) for value in row] for row in result.rows],
            "row_count": len(result.rows),
            "max_rows": max_rows,
        }


__all__ = ("SqlHTTPAdapter", "SqlQueryEngine")
