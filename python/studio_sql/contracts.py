"""Provider-neutral SQL execution contracts for Ronin Public v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class SqlValidationError(ValueError):
    """The submitted SQL request is malformed or not permitted."""


class SqlRelationUnavailableError(LookupError):
    """A referenced relation is not available in the selected project."""


class SqlExecutionError(RuntimeError):
    """The SQL backend failed while executing an otherwise valid request."""


class SqlTimeoutError(TimeoutError):
    """The SQL backend exceeded its execution deadline."""


@dataclass(frozen=True, slots=True)
class SqlColumn:
    name: str
    type_name: str

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip():
            raise ValueError("SQL column name must be non-empty and trimmed")
        if not self.type_name or self.type_name != self.type_name.strip():
            raise ValueError("SQL column type must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class SqlQueryResult:
    columns: tuple[SqlColumn, ...]
    rows: tuple[tuple[object, ...], ...]

    def __post_init__(self) -> None:
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("SQL result rows must match result column width")


@runtime_checkable
class SqlEngine(Protocol):
    """Minimal synchronous SQL engine contract; async/service layers wrap this boundary."""

    def register_parquet(self, name: str, path: str) -> None: ...

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult: ...

    def close(self) -> None: ...


__all__ = (
    "SqlColumn", "SqlEngine", "SqlExecutionError", "SqlQueryResult",
    "SqlRelationUnavailableError", "SqlTimeoutError", "SqlValidationError",
)
