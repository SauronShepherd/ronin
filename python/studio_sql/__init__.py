"""Provider-neutral SQL contracts and optional local reference engine."""

from .contracts import SqlColumn, SqlEngine, SqlQueryResult
from .duckdb_engine import (
    DuckDbDependencyError,
    DuckDbSqlEngine,
    ProjectScopedDuckDbSqlEngine,
)

__all__ = (
    "DuckDbDependencyError",
    "DuckDbSqlEngine",
    "ProjectScopedDuckDbSqlEngine",
    "SqlColumn",
    "SqlEngine",
    "SqlQueryResult",
)
