"""Durable deployment-local scheduler leadership with generation fencing."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from studio_orchestrator import Instant, LeaseToken

from .scheduler_controller import SchedulerControllerStore, migrate_scheduler_controller
from .sqlite import open_database

_LEADERSHIP_SCHEMA_VERSION = 1
_LEADERSHIP_MIGRATIONS = {1: "scheduler_leadership_001.sql"}


class SchedulerLeadershipLost(RuntimeError):
    """Raised when scheduler authority no longer matches the durable leader lease."""


@dataclass(frozen=True, slots=True)
class SchedulerLeaderLease:
    owner: str
    lease_token: LeaseToken
    generation: int
    acquired_at: Instant
    lease_expires_at: Instant

    def __post_init__(self) -> None:
        if not self.owner or self.owner != self.owner.strip():
            raise ValueError("scheduler leader owner must be non-empty and trimmed")
        if self.generation < 1:
            raise ValueError("scheduler leader generation must be positive")
        if self.lease_expires_at <= self.acquired_at:
            raise ValueError("scheduler leader lease must expire after acquisition")


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def _add_seconds(value: Instant | str, seconds: int) -> Instant:
    parsed = datetime.strptime(str(Instant(value)), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    return Instant(
        (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )


def migrate_scheduler_leadership(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    current_time = Instant(now)
    migrate_scheduler_controller(connection, now=current_time)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_leadership_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_leadership_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _LEADERSHIP_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler leadership schema {current} is newer than supported "
            f"{_LEADERSHIP_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _LEADERSHIP_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_LEADERSHIP_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_leadership_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, current_time),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_leadership_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_leadership_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _lease_from_row(row: sqlite3.Row) -> SchedulerLeaderLease:
    return SchedulerLeaderLease(
        owner=row["owner"],
        lease_token=LeaseToken(row["lease_token"]),
        generation=int(row["generation"]),
        acquired_at=Instant(row["acquired_at"]),
        lease_expires_at=Instant(row["lease_expires_at"]),
    )


class SchedulerLeadershipStore(SchedulerControllerStore):
    """Controller store with one durable scheduler leader lease per metadata plane."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_leadership(connection, now=migration_now)
        finally:
            connection.close()

    def get_scheduler_leader(self) -> SchedulerLeaderLease | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT owner,lease_token,generation,acquired_at,lease_expires_at "
                "FROM scheduler_leader_lease WHERE scope='scheduler'"
            ).fetchone()
            return None if row is None else _lease_from_row(row)
        finally:
            connection.close()

    def acquire_scheduler_leadership(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        lease_seconds: int,
        now: Instant | str,
    ) -> SchedulerLeaderLease | None:
        if not owner or owner != owner.strip():
            raise ValueError("scheduler leader owner must be non-empty and trimmed")
        if lease_seconds < 1:
            raise ValueError("scheduler leader lease_seconds must be positive")
        current = Instant(now)
        expires = _add_seconds(current, lease_seconds)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scheduler_leader_lease WHERE scope='scheduler'"
            ).fetchone()
            if row is None:
                generation = 1
            else:
                existing = _lease_from_row(row)
                if existing.lease_expires_at > current:
                    if existing.owner == owner and existing.lease_token == lease_token:
                        connection.execute("COMMIT")
                        return existing
                    connection.execute("COMMIT")
                    return None
                generation = existing.generation + 1
            lease = SchedulerLeaderLease(owner, lease_token, generation, current, expires)
            connection.execute(
                "INSERT INTO scheduler_leader_lease("
                "scope,owner,lease_token,generation,acquired_at,lease_expires_at,updated_at) "
                "VALUES ('scheduler',?,?,?,?,?,?) "
                "ON CONFLICT(scope) DO UPDATE SET owner=excluded.owner,"
                "lease_token=excluded.lease_token,generation=excluded.generation,"
                "acquired_at=excluded.acquired_at,lease_expires_at=excluded.lease_expires_at,"
                "updated_at=excluded.updated_at",
                (
                    lease.owner,
                    str(lease.lease_token),
                    lease.generation,
                    lease.acquired_at,
                    lease.lease_expires_at,
                    current,
                ),
            )
            connection.execute("COMMIT")
            return lease
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def assert_scheduler_leadership(
        self,
        lease: SchedulerLeaderLease,
        *,
        now: Instant | str,
    ) -> SchedulerLeaderLease:
        current = Instant(now)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM scheduler_leader_lease WHERE scope='scheduler'"
            ).fetchone()
            if row is None:
                raise SchedulerLeadershipLost("scheduler leader lease does not exist")
            durable = _lease_from_row(row)
            if (
                durable.owner != lease.owner
                or durable.lease_token != lease.lease_token
                or durable.generation != lease.generation
                or durable.lease_expires_at <= current
            ):
                raise SchedulerLeadershipLost("scheduler leadership lost")
            return durable
        finally:
            connection.close()

    def heartbeat_scheduler_leadership(
        self,
        lease: SchedulerLeaderLease,
        *,
        lease_seconds: int,
        now: Instant | str,
    ) -> SchedulerLeaderLease:
        if lease_seconds < 1:
            raise ValueError("scheduler leader lease_seconds must be positive")
        current = Instant(now)
        expires = _add_seconds(current, lease_seconds)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scheduler_leader_lease WHERE scope='scheduler'"
            ).fetchone()
            if row is None:
                raise SchedulerLeadershipLost("scheduler leader lease does not exist")
            durable = _lease_from_row(row)
            if (
                durable.owner != lease.owner
                or durable.lease_token != lease.lease_token
                or durable.generation != lease.generation
                or durable.lease_expires_at <= current
            ):
                raise SchedulerLeadershipLost("scheduler leadership lost")
            updated = SchedulerLeaderLease(
                durable.owner,
                durable.lease_token,
                durable.generation,
                durable.acquired_at,
                expires,
            )
            connection.execute(
                "UPDATE scheduler_leader_lease SET lease_expires_at=?,updated_at=? "
                "WHERE scope='scheduler' AND owner=? AND lease_token=? AND generation=?",
                (
                    updated.lease_expires_at,
                    current,
                    updated.owner,
                    str(updated.lease_token),
                    updated.generation,
                ),
            )
            connection.execute("COMMIT")
            return updated
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def release_scheduler_leadership(
        self,
        lease: SchedulerLeaderLease,
        *,
        now: Instant | str,
    ) -> None:
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM scheduler_leader_lease WHERE scope='scheduler'"
            ).fetchone()
            if row is None:
                raise SchedulerLeadershipLost("scheduler leader lease does not exist")
            durable = _lease_from_row(row)
            if (
                durable.owner != lease.owner
                or durable.lease_token != lease.lease_token
                or durable.generation != lease.generation
            ):
                raise SchedulerLeadershipLost("scheduler leadership lost")
            connection.execute(
                "UPDATE scheduler_leader_lease SET lease_expires_at=?,updated_at=? "
                "WHERE scope='scheduler'",
                (current, current),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = (
    "SchedulerLeaderLease",
    "SchedulerLeadershipLost",
    "SchedulerLeadershipStore",
    "migrate_scheduler_leadership",
    "scheduler_leadership_schema_version",
)
