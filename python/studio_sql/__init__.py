"""Provider-neutral SQL contracts and optional local reference engine."""

from .contracts import SqlColumn, SqlEngine, SqlQueryResult
from .duckdb_engine import DuckDbDependencyError, DuckDbSqlEngine

__all__ = (
    "DuckDbDependencyError",
    "DuckDbSqlEngine",
    "SqlColumn",
    "SqlEngine",
    "SqlQueryResult",
)
