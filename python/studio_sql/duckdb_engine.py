"""Optional DuckDB-backed local SQL reference engine."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .contracts import (
    SqlColumn,
    SqlExecutionError,
    SqlQueryResult,
    SqlRelationUnavailableError,
    SqlValidationError,
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SELECT_START = re.compile(r"^SELECT\b", re.IGNORECASE)
_MAX_SQL_BYTES = 1024 * 1024
_UNSAFE_SQL = re.compile(
    r"\b(?:read_(?:parquet|csv|json|blob)|http(?:fs|_get)?|sqlite_scan|postgres_scan|"
    r"delta_scan|iceberg_scan|glob|pragma(?:_[a-z_]+)?|install|load|attach|copy|export|import|"
    r"insert|update|delete|create|drop|alter|set|call)\b|(?:https?|s3|gs)://",
    re.IGNORECASE,
)
_FROM_CLAUSE_END = frozenset(
    {
        "except",
        "fetch",
        "group",
        "having",
        "intersect",
        "limit",
        "offset",
        "order",
        "qualify",
        "sample",
        "union",
        "where",
        "window",
    }
)


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


def _sql_tokens(sql: str) -> list[tuple[str, str, int]]:
    """Tokenize enough SQL syntax to fail closed on unregistered FROM sources.

    DuckDB accepts file paths as table references (for example, ``FROM
    '/tmp/data.parquet'``), so checking only for known file-reading functions
    is not a sufficient filesystem boundary. This scanner deliberately does
    not parse arbitrary SQL; it identifies every relation source and rejects
    forms it cannot prove refer only to an explicitly registered relation.
    DuckDB remains the authoritative syntax parser after this policy check.
    """
    tokens: list[tuple[str, str, int]] = []
    index = 0
    depth = 0
    size = len(sql)
    while index < size:
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            index = size if newline < 0 else newline + 1
            continue
        if sql.startswith("/*", index):
            index += 2
            comment_depth = 1
            while index < size and comment_depth:
                if sql.startswith("/*", index):
                    comment_depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    comment_depth -= 1
                    index += 2
                else:
                    index += 1
            continue
        if char == "$":
            delimiter_match = re.match(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$", sql[index:])
            if delimiter_match is not None:
                delimiter = delimiter_match.group(0)
                content_start = index + len(delimiter)
                closing = sql.find(delimiter, content_start)
                content_end = size if closing < 0 else closing
                tokens.append(("string", sql[content_start:content_end], depth))
                index = size if closing < 0 else closing + len(delimiter)
                continue
        if char in "'\"`":
            quote = char
            start = index + 1
            index += 1
            value: list[str] = []
            while index < size:
                if sql[index] == quote:
                    if index + 1 < size and sql[index + 1] == quote:
                        value.append(sql[start:index])
                        value.append(quote)
                        index += 2
                        start = index
                        continue
                    value.append(sql[start:index])
                    index += 1
                    break
                if sql[index] == "\\" and index + 1 < size:
                    index += 2
                    continue
                index += 1
            kind = "string" if quote == "'" else "quoted_identifier"
            tokens.append((kind, "".join(value), depth))
            continue
        if char == "(":
            tokens.append(("symbol", char, depth))
            depth += 1
            index += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            tokens.append(("symbol", char, depth))
            index += 1
            continue
        if char.isascii() and (char.isalpha() or char == "_"):
            end = index + 1
            while end < size and sql[end].isascii() and (sql[end].isalnum() or sql[end] in "_$"):
                end += 1
            tokens.append(("identifier", sql[index:end], depth))
            index = end
            continue
        tokens.append(("symbol", char, depth))
        index += 1
    return tokens


def _validate_relation_sources(sql: str, registered_relations: set[str]) -> None:
    tokens = _sql_tokens(sql)

    def is_keyword(position: int, keyword: str) -> bool:
        return (
            position < len(tokens)
            and tokens[position][0] == "identifier"
            and tokens[position][1].casefold() == keyword
        )

    def validate_source(position: int) -> int:
        if position >= len(tokens):
            raise SqlValidationError("SQL relation source is incomplete")
        lexeme_type, lexeme_text, source_depth = tokens[position]
        if lexeme_type == "symbol" and lexeme_text == "(":
            inner = position + 1
            if not is_keyword(inner, "select"):
                raise SqlValidationError(
                    "SQL table expressions must be SELECT subqueries over registered relations"
                )
            nested_depth = source_depth + 1
            closing = next(
                (
                    cursor
                    for cursor in range(inner + 1, len(tokens))
                    if tokens[cursor] == ("symbol", ")", nested_depth - 1)
                ),
                None,
            )
            if closing is None:
                raise SqlValidationError("SQL subquery is not closed")
            return closing + 1
        if lexeme_type == "string":
            raise SqlValidationError(
                "SQL file paths cannot be used as relations; register the Parquet asset first"
            )
        if lexeme_type not in {"identifier", "quoted_identifier"}:
            raise SqlValidationError("SQL relation source must be a registered relation")
        relation = lexeme_text
        after = position + 1
        if after < len(tokens) and tokens[after] == ("symbol", ".", source_depth):
            if after + 1 >= len(tokens) or tokens[after + 1][0] not in {
                "identifier",
                "quoted_identifier",
            }:
                raise SqlValidationError("SQL relation name is malformed")
            schema = relation
            relation = tokens[after + 1][1]
            if schema.casefold() != "main":
                raise SqlValidationError("SQL relations must use the registered main schema")
            after += 2
        if after < len(tokens) and tokens[after] == ("symbol", "(", source_depth):
            raise SqlValidationError(
                "SQL table functions are disabled; register the Parquet asset first"
            )
        if relation.casefold() not in registered_relations:
            raise SqlRelationUnavailableError("requested SQL relation is unavailable")
        return after

    for index, (kind, value, depth) in enumerate(tokens):
        if kind != "identifier" or value.casefold() not in {"from", "join"}:
            continue
        next_position = validate_source(index + 1)
        if value.casefold() != "from":
            continue
        in_join_condition = False
        for cursor in range(next_position, len(tokens)):
            lexeme_type, lexeme_text, token_depth = tokens[cursor]
            if token_depth < depth:
                break
            if token_depth != depth or lexeme_type != "identifier":
                if token_depth == depth and lexeme_text == ",":
                    if in_join_condition:
                        raise SqlValidationError("comma joins in JOIN conditions are disabled")
                    validate_source(cursor + 1)
                continue
            keyword = lexeme_text.casefold()
            if keyword in _FROM_CLAUSE_END:
                break
            if keyword == "join":
                in_join_condition = False
            elif keyword == "on":
                in_join_condition = True
            elif keyword in {"where", "using"}:
                in_join_condition = False


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

    def list_relations(self) -> tuple[str, ...]:
        self._require_open()
        rows = self._connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def drop_relation(self, name: str) -> None:
        self._require_open()
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError("SQL relation name must be a simple identifier")
        if name not in self.list_relations():
            raise SqlRelationUnavailableError("requested SQL relation is unavailable")
        quoted = '"' + name.replace('"', '""') + '"'
        try:
            self._connection.execute(f"DROP VIEW {quoted}")
        except Exception as exc:
            raise SqlExecutionError("SQL relation removal failed") from exc

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        self._require_open()
        if not sql or sql != sql.strip():
            raise SqlValidationError("SQL text must be non-empty and trimmed")
        if len(sql.encode("utf-8")) > _MAX_SQL_BYTES:
            raise SqlValidationError("SQL text exceeds the configured byte limit")
        if ";" in sql or not _SELECT_START.match(sql):
            raise SqlValidationError("SQL engine accepts one read-only SELECT statement")
        if _UNSAFE_SQL.search(sql):
            raise SqlValidationError("SQL external filesystem and network access is disabled")
        if max_rows < 1:
            raise SqlValidationError("max_rows must be positive")
        _validate_relation_sources(sql, {name.casefold() for name in self.list_relations()})

        try:
            cursor = self._connection.execute(sql, parameters)
        except Exception as exc:
            message = str(exc).lower()
            if "table with name" in message or "does not exist" in message:
                raise SqlRelationUnavailableError("requested SQL relation is unavailable") from exc
            if "binder error" in message or "column" in message:
                raise SqlValidationError("SQL query references an invalid column") from exc
            raise SqlExecutionError("SQL backend execution failed") from exc
        description = cursor.description or ()
        columns = tuple(SqlColumn(item[0], str(item[1])) for item in description)
        rows = tuple(tuple(row) for row in cursor.fetchmany(max_rows + 1))
        if len(rows) > max_rows:
            raise SqlValidationError("SQL result exceeds max_rows; use a more selective query")
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


class ProjectScopedDuckDbSqlEngine:
    """DuckDB reference engine with independent relation namespaces per project."""

    def __init__(self) -> None:
        self._engines: dict[str, DuckDbSqlEngine] = {}
        self._engine_locks: dict[str, threading.RLock] = {}
        self._lock = threading.RLock()
        self._closed = False

    @contextmanager
    def _project_engine(self, project: str) -> Iterator[DuckDbSqlEngine]:
        if not project or project != project.strip():
            raise ValueError("SQL project must be non-empty and trimmed")
        with self._lock:
            if self._closed:
                raise RuntimeError("SQL engine is closed")
            engine = self._engines.get(project)
            if engine is None:
                engine = DuckDbSqlEngine()
                self._engines[project] = engine
                self._engine_locks[project] = threading.RLock()
            operation_lock = self._engine_locks[project]
            # Acquire before releasing the registry lock so close() cannot
            # overtake an operation that has already passed the open check.
            operation_lock.acquire()
        try:
            yield engine
        finally:
            operation_lock.release()

    def register_parquet(self, project: str, name: str, path: str) -> None:
        with self._project_engine(project) as engine:
            engine.register_parquet(name, path)

    def list_relations(self, project: str) -> tuple[str, ...]:
        with self._project_engine(project) as engine:
            return engine.list_relations()

    def drop_relation(self, project: str, name: str) -> None:
        with self._project_engine(project) as engine:
            engine.drop_relation(name)

    def execute(
        self,
        project: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        with self._project_engine(project) as engine:
            return engine.execute(sql, parameters, max_rows=max_rows)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            engines = tuple(self._engines.values())
            locks = tuple(self._engine_locks.values())
            self._engines.clear()
            self._engine_locks.clear()
            for engine, operation_lock in zip(engines, locks, strict=True):
                with operation_lock:
                    engine.close()

    def __enter__(self) -> ProjectScopedDuckDbSqlEngine:
        with self._lock:
            if self._closed:
                raise RuntimeError("SQL engine is closed")
            return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


__all__ = ("DuckDbDependencyError", "DuckDbSqlEngine", "ProjectScopedDuckDbSqlEngine")
