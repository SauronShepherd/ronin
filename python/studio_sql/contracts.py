"""Provider-neutral SQL execution contracts for Ronin Public v1."""

from __future__ import annotations

import math
import re
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


class SqlResultLimitError(ValueError):
    """The serialized SQL result exceeds its configured response budget."""


class SqlExplainUnsupportedError(SqlExecutionError):
    """The selected SQL provider does not expose the explain capability."""


_READ_ONLY_SELECT = re.compile(r"^SELECT\b", re.IGNORECASE)
_MAX_SQL_PARAMETER_COUNT = 1_000
_MAX_SQL_PARAMETER_TEXT_LENGTH = 524_288
_SQL_PARAMETER_TYPES = frozenset({"null", "boolean", "integer", "float", "string"})


def normalize_sql_parameters(value: object) -> tuple[object, ...]:
    """Validate SQL scalar bindings and normalize tagged or legacy JSON values.

    Tagged values use ``{"type": ..., "value": ...}`` so clients can state
    the intended SQL scalar type explicitly. Existing JSON scalar bindings
    remain accepted for v1 compatibility and retain their JSON-derived type.
    """
    if not isinstance(value, list):
        raise SqlValidationError("SQL parameters must be an array")
    if len(value) > _MAX_SQL_PARAMETER_COUNT:
        raise SqlValidationError("SQL parameters exceed the configured count limit")

    normalized: list[object] = []
    for index, parameter in enumerate(value):
        if isinstance(parameter, dict):
            if set(parameter) != {"type", "value"}:
                raise SqlValidationError(f"SQL parameter {index} must contain only type and value")
            kind = parameter.get("type")
            item = parameter.get("value")
            if not isinstance(kind, str) or kind not in _SQL_PARAMETER_TYPES:
                raise SqlValidationError(f"SQL parameter {index} has an unsupported type")
            if kind == "null":
                if item is not None:
                    raise SqlValidationError(f"SQL parameter {index} does not match its type")
            elif kind == "boolean":
                if not isinstance(item, bool):
                    raise SqlValidationError(f"SQL parameter {index} does not match its type")
            elif kind == "integer":
                if isinstance(item, bool) or not isinstance(item, int):
                    raise SqlValidationError(f"SQL parameter {index} does not match its type")
                if not -(2**63) <= item < 2**63:
                    raise SqlValidationError(
                        f"SQL parameter {index} is outside the signed 64-bit range"
                    )
            elif kind == "float":
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise SqlValidationError(f"SQL parameter {index} must be a finite float")
                try:
                    item = float(item)
                except OverflowError as exc:
                    raise SqlValidationError(
                        f"SQL parameter {index} must be a finite float"
                    ) from exc
                if not math.isfinite(item):
                    raise SqlValidationError(f"SQL parameter {index} must be a finite float")
            elif kind == "string":
                if not isinstance(item, str):
                    raise SqlValidationError(f"SQL parameter {index} does not match its type")
                if len(item) > _MAX_SQL_PARAMETER_TEXT_LENGTH:
                    raise SqlValidationError(f"SQL parameter {index} exceeds the text limit")
            normalized.append(item)
            continue

        if parameter is None or isinstance(parameter, (bool, str)):
            if isinstance(parameter, str) and len(parameter) > _MAX_SQL_PARAMETER_TEXT_LENGTH:
                raise SqlValidationError(f"SQL parameter {index} exceeds the text limit")
            normalized.append(parameter)
        elif isinstance(parameter, int):
            if not -(2**63) <= parameter < 2**63:
                raise SqlValidationError(
                    f"SQL parameter {index} is outside the signed 64-bit range"
                )
            normalized.append(parameter)
        elif isinstance(parameter, float) and math.isfinite(parameter):
            normalized.append(parameter)
        else:
            raise SqlValidationError(f"SQL parameter {index} must be a finite JSON scalar")
    return tuple(normalized)


def validate_read_only_select(sql: str) -> None:
    """Enforce the supported statement subset on every SQL execution path.

    CTEs, VALUES and EXPLAIN can be added when the shared contract and all
    exposed engines implement the same semantics.
    """
    if not sql or sql != sql.strip():
        raise SqlValidationError("SQL text must be non-empty and trimmed")
    if ";" in sql or not _READ_ONLY_SELECT.match(sql):
        raise SqlValidationError("SQL engine accepts one read-only SELECT statement")


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


@dataclass(frozen=True, slots=True)
class SqlExplainResult:
    """Bounded, provider-neutral explain output.

    Providers return already-sanitized textual plan rows. The contract never
    exposes filesystem paths, credentials, or backend connection details.
    """

    rows: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if any(len(row) != 2 or any(not isinstance(value, str) for value in row) for row in self.rows):
            raise ValueError("SQL explain rows must contain two text values")


@runtime_checkable
class SqlEngine(Protocol):
    """Minimal synchronous SQL engine contract; async/service layers wrap this boundary."""

    def register_parquet(self, name: str, path: str) -> None: ...

    def list_relations(self) -> tuple[str, ...]: ...

    def drop_relation(self, name: str) -> None: ...

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
        timeout_ms: int = 5_000,
        max_result_bytes: int = 1_048_576,
    ) -> SqlQueryResult: ...

    def explain(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_bytes: int = 262_144,
    ) -> SqlExplainResult: ...

    def close(self) -> None: ...


__all__ = (
    "SqlColumn",
    "SqlEngine",
    "SqlExecutionError",
    "SqlExplainResult",
    "SqlExplainUnsupportedError",
    "SqlQueryResult",
    "SqlResultLimitError",
    "SqlRelationUnavailableError",
    "SqlTimeoutError",
    "SqlValidationError",
    "normalize_sql_parameters",
    "validate_read_only_select",
)
