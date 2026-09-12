"""Durable scheduler-task to execution-job links under scheduler lease fencing."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from studio_core import WorkspaceId
from studio_orchestrator import Instant, JobId, LeaseToken

from .scheduler_fencing import (
    FencedSqliteSchedulerStore,
    TaskAttemptId,
    migrate_scheduler_fencing,
)
from .sqlite import open_database

_EXECUTION_LINK_SCHEMA_VERSION = 1
_EXECUTION_LINK_MIGRATIONS = {1: "scheduler_execution_001.sql"}


class TaskExecutionLinkConflict(RuntimeError):
    """Raised when a task attempt is rebound to different execution identity."""


@dataclass(frozen=True, slots=True)
class TaskExecutionLink:
    workspace_id: WorkspaceId
    task_attempt_id: TaskAttemptId
    job_id: JobId
    request_digest: str

    def __post_init__(self) -> None:
        if len(self.request_digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.request_digest
        ):
            raise ValueError("request_digest must be lowercase sha256 hex")


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_execution(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_scheduler_fencing(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_execution_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_execution_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _EXECUTION_LINK_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler execution schema {current} is newer than supported "
            f"{_EXECUTION_LINK_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _EXECUTION_LINK_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_EXECUTION_LINK_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_execution_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_execution_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_execution_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SchedulerExecutionLinkStore(FencedSqliteSchedulerStore):
    """Fenced scheduler store extended with durable task-attempt execution links."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_execution(connection, now=migration_now)
        finally:
            connection.close()

    def bind_execution(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
        *,
        job_id: JobId,
        request_digest: str,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> TaskExecutionLink:
        current = Instant(now)
        link = TaskExecutionLink(workspace_id, attempt_id, job_id, request_digest)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._active_attempt(
                connection,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            existing = connection.execute(
                "SELECT job_id,request_digest FROM task_execution_links "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if existing is not None:
                if existing["job_id"] != str(job_id) or existing["request_digest"] != request_digest:
                    raise TaskExecutionLinkConflict(
                        "task attempt is already bound to different execution identity"
                    )
                connection.execute("COMMIT")
                return link
            connection.execute(
                "INSERT INTO task_execution_links("
                "workspace_id,task_attempt_id,job_id,request_digest,created_at) VALUES (?,?,?,?,?)",
                (str(workspace_id), str(attempt_id), str(job_id), request_digest, current),
            )
            connection.execute("COMMIT")
            return link
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_execution_link(
        self,
        workspace_id: WorkspaceId,
        attempt_id: TaskAttemptId,
    ) -> TaskExecutionLink | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT job_id,request_digest FROM task_execution_links "
                "WHERE workspace_id=? AND task_attempt_id=?",
                (str(workspace_id), str(attempt_id)),
            ).fetchone()
            if row is None:
                return None
            return TaskExecutionLink(
                workspace_id,
                attempt_id,
                JobId(row["job_id"]),
                row["request_digest"],
            )
        finally:
            connection.close()


__all__ = (
    "SchedulerExecutionLinkStore",
    "TaskExecutionLink",
    "TaskExecutionLinkConflict",
    "migrate_scheduler_execution",
    "scheduler_execution_schema_version",
)
