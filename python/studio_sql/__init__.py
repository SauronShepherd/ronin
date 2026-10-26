"""Provider-neutral SQL contracts and optional local reference engine."""

from .contracts import (
    SqlColumn,
    SqlEngine,
    SqlExecutionError,
    SqlQueryResult,
    SqlRelationUnavailableError,
    SqlTimeoutError,
    SqlValidationError,
    validate_read_only_select,
)
from .duckdb_engine import (
    DuckDbDependencyError,
    DuckDbSqlEngine,
    ProjectScopedDuckDbSqlEngine,
)
from .http import SqlHTTPAdapter, SqlQueryEngine

__all__ = (
    "DuckDbDependencyError",
    "DuckDbSqlEngine",
    "ProjectScopedDuckDbSqlEngine",
    "SqlColumn",
    "SqlHTTPAdapter",
    "SqlEngine",
    "SqlExecutionError",
    "SqlQueryResult",
    "SqlQueryEngine",
    "SqlRelationUnavailableError",
    "SqlTimeoutError",
    "SqlValidationError",
    "validate_read_only_select",
)
