"""Durable QueryFlux lifecycle invariants shared by HTTP and worker layers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from studio_storage.postgres_core import _psycopg
from studio_storage.sqlite import open_database

QueryFluxState = Literal["queued", "running", "cancelling", "succeeded", "failed", "cancelled"]
QueryFluxTerminalState = Literal["succeeded", "failed", "cancelled"]

_TRANSITIONS: dict[QueryFluxState, frozenset[QueryFluxState]] = {
    "queued": frozenset({"running", "cancelling", "failed", "cancelled"}),
    "running": frozenset({"cancelling", "succeeded", "failed", "cancelled"}),
    "cancelling": frozenset({"cancelled", "failed"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


@dataclass(frozen=True, slots=True)
class QueryFluxExecution:
    """Identity and state needed to resume one scoped QueryFlux attempt."""

    workspace_id: str
    project_id: str
    run_id: str
    attempt_id: str
    state: QueryFluxState = "queued"
    cancel_requested: bool = False
    failure_code: str | None = None

    def request_cancel(self) -> QueryFluxExecution:
        """Record cancellation intent without mutating terminal executions."""

        if self.state in {"succeeded", "failed", "cancelled"}:
            return self
        if self.state == "cancelling":
            return replace(self, cancel_requested=True)
        return replace(self, state="cancelling", cancel_requested=True)

    def transition(
        self,
        state: QueryFluxState,
        *,
        failure_code: str | None = None,
    ) -> QueryFluxExecution:
        """Apply one lifecycle transition, rejecting illegal state changes."""

        if state == self.state:
            return replace(self, failure_code=failure_code or self.failure_code)
        if state == "succeeded" and self.cancel_requested:
            raise ValueError("a cancellation-requested QueryFlux execution cannot succeed")
        if state not in _TRANSITIONS[self.state]:
            raise ValueError(f"invalid QueryFlux transition: {self.state} -> {state}")
        if state == "failed" and not failure_code and not self.failure_code:
            raise ValueError("failed QueryFlux execution requires a failure_code")
        return replace(self, state=state, failure_code=failure_code or self.failure_code)

    @property
    def terminal(self) -> bool:
        return self.state in {"succeeded", "failed", "cancelled"}


class SqliteQueryFluxExecutionStore:
    """SQLite persistence for the QueryFlux lifecycle boundary."""

    def __init__(self, path: Path) -> None:
        self._path = path
        connection = open_database(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS de_queryflux_executions ("
                "workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                "run_id TEXT NOT NULL, attempt_id TEXT NOT NULL, state TEXT NOT NULL,"
                "cancel_requested INTEGER NOT NULL DEFAULT 0, failure_code TEXT NULL,"
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                "PRIMARY KEY(workspace_id,project_id,run_id,attempt_id))"
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    @staticmethod
    def _identity(execution: QueryFluxExecution) -> tuple[str, str, str, str]:
        values = (
            execution.workspace_id,
            execution.project_id,
            execution.run_id,
            execution.attempt_id,
        )
        if any(not value or value != value.strip() for value in values):
            raise ValueError("QueryFlux execution identity must be non-empty and trimmed")
        return values

    def create(self, execution: QueryFluxExecution) -> QueryFluxExecution:
        identity = self._identity(execution)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO de_queryflux_executions "
                "(workspace_id,project_id,run_id,attempt_id,state,cancel_requested,failure_code) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    *identity,
                    execution.state,
                    int(execution.cancel_requested),
                    execution.failure_code,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get(*identity)
        if stored is None:
            raise RuntimeError("QueryFlux execution was not persisted")
        return stored

    def get(
        self, workspace_id: str, project_id: str, run_id: str, attempt_id: str
    ) -> QueryFluxExecution | None:
        values = (workspace_id, project_id, run_id, attempt_id)
        if any(not value or value != value.strip() for value in values):
            raise ValueError("QueryFlux execution identity must be non-empty and trimmed")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT workspace_id,project_id,run_id,attempt_id,state,"
                "cancel_requested,failure_code FROM de_queryflux_executions "
                "WHERE workspace_id=? AND project_id=? AND run_id=? AND attempt_id=?",
                values,
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return QueryFluxExecution(
            row["workspace_id"],
            row["project_id"],
            row["run_id"],
            row["attempt_id"],
            row["state"],
            bool(row["cancel_requested"]),
            row["failure_code"],
        )

    def transition(self, execution: QueryFluxExecution) -> QueryFluxExecution:
        identity = self._identity(execution)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT workspace_id,project_id,run_id,attempt_id,state,"
                "cancel_requested,failure_code FROM de_queryflux_executions "
                "WHERE workspace_id=? AND project_id=? AND run_id=? AND attempt_id=?",
                identity,
            ).fetchone()
            if row is None:
                raise KeyError("QueryFlux execution does not exist")
            current = QueryFluxExecution(
                row["workspace_id"],
                row["project_id"],
                row["run_id"],
                row["attempt_id"],
                row["state"],
                bool(row["cancel_requested"]),
                row["failure_code"],
            )
            if execution.cancel_requested and current.terminal:
                connection.commit()
                return current
            next_execution = current.transition(
                execution.state, failure_code=execution.failure_code
            )
            if execution.cancel_requested and not next_execution.cancel_requested:
                next_execution = replace(next_execution, cancel_requested=True)
            connection.execute(
                "UPDATE de_queryflux_executions SET state=?,cancel_requested=?,failure_code=?,"
                "updated_at=CURRENT_TIMESTAMP WHERE workspace_id=? AND project_id=? "
                "AND run_id=? AND attempt_id=?",
                (
                    next_execution.state,
                    int(next_execution.cancel_requested),
                    next_execution.failure_code,
                    *identity,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get(*identity)  # type: ignore[return-value]

    def request_cancel(self, execution: QueryFluxExecution) -> QueryFluxExecution:
        return self.transition(execution.request_cancel())


class PostgresQueryFluxExecutionStore:
    """PostgreSQL persistence for the QueryFlux lifecycle boundary."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-queryflux-lifecycle") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name
        self.migrate()

    def _connect(self) -> Any:
        psycopg, _dict_row = _psycopg()
        return psycopg.connect(self._dsn, autocommit=False, application_name=self._application_name)

    def migrate(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_de_queryflux_executions ("
                    "workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,"
                    "run_id TEXT NOT NULL, attempt_id TEXT NOT NULL, state TEXT NOT NULL,"
                    "cancel_requested BOOLEAN NOT NULL DEFAULT FALSE, failure_code TEXT NULL,"
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "PRIMARY KEY(workspace_id,project_id,run_id,attempt_id))"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _identity(execution: QueryFluxExecution) -> tuple[str, str, str, str]:
        return SqliteQueryFluxExecutionStore._identity(execution)

    def create(self, execution: QueryFluxExecution) -> QueryFluxExecution:
        identity = self._identity(execution)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_de_queryflux_executions "
                    "(workspace_id,project_id,run_id,attempt_id,state,cancel_requested,"
                    "failure_code) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (
                        *identity,
                        execution.state,
                        execution.cancel_requested,
                        execution.failure_code,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get(*identity)
        if stored is None:
            raise RuntimeError("QueryFlux execution was not persisted")
        return stored

    def get(
        self, workspace_id: str, project_id: str, run_id: str, attempt_id: str
    ) -> QueryFluxExecution | None:
        identity = (workspace_id, project_id, run_id, attempt_id)
        if any(not value or value != value.strip() for value in identity):
            raise ValueError("QueryFlux execution identity must be non-empty and trimmed")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT workspace_id,project_id,run_id,attempt_id,state,"
                    "cancel_requested,failure_code FROM ronin_de_queryflux_executions "
                    "WHERE workspace_id=%s AND project_id=%s AND run_id=%s AND attempt_id=%s",
                    identity,
                )
                row = cursor.fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return QueryFluxExecution(*row)

    def transition(self, execution: QueryFluxExecution) -> QueryFluxExecution:
        identity = self._identity(execution)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT workspace_id,project_id,run_id,attempt_id,state,"
                    "cancel_requested,failure_code FROM ronin_de_queryflux_executions "
                    "WHERE workspace_id=%s AND project_id=%s AND run_id=%s "
                    "AND attempt_id=%s FOR UPDATE",
                    identity,
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError("QueryFlux execution does not exist")
                current = QueryFluxExecution(*row)
                if execution.cancel_requested and current.terminal:
                    connection.commit()
                    return current
                next_execution = current.transition(
                    execution.state, failure_code=execution.failure_code
                )
                if execution.cancel_requested and not next_execution.cancel_requested:
                    next_execution = replace(next_execution, cancel_requested=True)
                cursor.execute(
                    "UPDATE ronin_de_queryflux_executions SET state=%s,cancel_requested=%s,"
                    "failure_code=%s,updated_at=CURRENT_TIMESTAMP WHERE workspace_id=%s "
                    "AND project_id=%s AND run_id=%s AND attempt_id=%s",
                    (
                        next_execution.state,
                        next_execution.cancel_requested,
                        next_execution.failure_code,
                        *identity,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get(*identity)  # type: ignore[return-value]

    def request_cancel(self, execution: QueryFluxExecution) -> QueryFluxExecution:
        return self.transition(execution.request_cancel())


__all__ = (
    "QueryFluxExecution",
    "QueryFluxState",
    "QueryFluxTerminalState",
    "SqliteQueryFluxExecutionStore",
    "PostgresQueryFluxExecutionStore",
)
