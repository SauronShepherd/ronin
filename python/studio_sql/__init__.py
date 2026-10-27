"""Provider-neutral SQL contracts and optional local reference engine."""

from .contracts import (
    SqlColumn,
    SqlEngine,
    SqlExecutionError,
    SqlExplainResult,
    SqlExplainUnsupportedError,
    SqlQueryResult,
    SqlRelationUnavailableError,
    SqlResultLimitError,
    SqlTimeoutError,
    SqlValidationError,
    normalize_sql_parameters,
    sanitize_sql_explain_text,
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
    "SqlExplainResult",
    "SqlExplainUnsupportedError",
    "SqlQueryResult",
    "SqlResultLimitError",
    "SqlQueryEngine",
    "SqlRelationUnavailableError",
    "SqlTimeoutError",
    "SqlValidationError",
    "normalize_sql_parameters",
    "sanitize_sql_explain_text",
    "validate_read_only_select",
)
