"""Generation-fenced PostgreSQL scheduler leadership persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from studio_orchestrator import Instant, LeaseToken

from .postgres_scheduler import PostgresSchedulerSnapshotStore
from .scheduler_leadership import (
    SchedulerLeaderLease,
    SchedulerLeadershipLost,
)

_SCHEMA_VERSION = 1


class PostgresSchedulerLeadershipStore(PostgresSchedulerSnapshotStore):
    """PostgreSQL persistence for a single generation-fenced scheduler leader."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-scheduler-leadership") -> None:
        super().__init__(dsn, application_name=application_name)
        self.migrate_leadership()

    def migrate_leadership(self) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("ronin:postgres-scheduler-leadership",),
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_scheduler_leadership_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                cursor.execute(
                    "SELECT COALESCE(MAX(version),0) AS version "
                    "FROM ronin_scheduler_leadership_migrations"
                )
                current = int(cursor.fetchone()["version"])
                if current > _SCHEMA_VERSION:
                    raise RuntimeError(
                        f"PostgreSQL scheduler leadership schema {current} is newer than "
                        f"supported {_SCHEMA_VERSION}"
                    )
                if current == 0:
                    cursor.execute(
                        "CREATE TABLE ronin_scheduler_leader_lease ("
                        "scope TEXT PRIMARY KEY CHECK (scope='scheduler'),"
                        "owner TEXT NOT NULL, lease_token TEXT NOT NULL,"
                        "generation BIGINT NOT NULL CHECK (generation >= 1),"
                        "acquired_at TEXT NOT NULL, lease_expires_at TEXT NOT NULL,"
                        "updated_at TEXT NOT NULL)"
                    )
                    cursor.execute(
                        "INSERT INTO ronin_scheduler_leadership_migrations(version,applied_at) "
                        "VALUES (%s,%s)",
                        (1, _now()),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_scheduler_leader(self) -> SchedulerLeaderLease | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT owner,lease_token,generation,acquired_at,lease_expires_at "
                    "FROM ronin_scheduler_leader_lease WHERE scope='scheduler'"
                )
                row = cursor.fetchone()
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
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_scheduler_leader_lease "
                    "(scope,owner,lease_token,generation,acquired_at,lease_expires_at,updated_at) "
                    "VALUES ('scheduler',%s,%s,1,%s,%s,%s) ON CONFLICT(scope) DO NOTHING",
                    (
                        owner,
                        str(lease_token),
                        str(current),
                        _add_seconds(current, lease_seconds),
                        str(current),
                    ),
                )
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_leader_lease WHERE scope='scheduler' FOR UPDATE"
                )
                row = cursor.fetchone()
                if row is None:
                    raise AssertionError("scheduler leader upsert returned no durable row")
                existing = _lease_from_row(row)
                if existing.lease_expires_at > current:
                    connection.commit()
                    if existing.owner == owner and existing.lease_token == lease_token:
                        return existing
                    return None
                lease = SchedulerLeaderLease(
                    owner,
                    lease_token,
                    existing.generation + 1,
                    current,
                    _add_seconds(current, lease_seconds),
                )
                cursor.execute(
                    "UPDATE ronin_scheduler_leader_lease SET owner=%s,lease_token=%s,"
                    "generation=%s,acquired_at=%s,lease_expires_at=%s,updated_at=%s "
                    "WHERE scope='scheduler'",
                    (
                        lease.owner,
                        str(lease.lease_token),
                        lease.generation,
                        str(lease.acquired_at),
                        str(lease.lease_expires_at),
                        str(current),
                    ),
                )
            connection.commit()
            return lease
        except Exception:
            connection.rollback()
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
        durable = self.get_scheduler_leader()
        return _require_current(durable, lease, current)

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
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_leader_lease WHERE scope='scheduler' FOR UPDATE"
                )
                row = cursor.fetchone()
                durable = None if row is None else _lease_from_row(row)
                durable = _require_current(durable, lease, current)
                updated = SchedulerLeaderLease(
                    durable.owner,
                    durable.lease_token,
                    durable.generation,
                    durable.acquired_at,
                    _add_seconds(current, lease_seconds),
                )
                cursor.execute(
                    "UPDATE ronin_scheduler_leader_lease SET lease_expires_at=%s,updated_at=%s "
                    "WHERE scope='scheduler' AND owner=%s AND lease_token=%s AND generation=%s",
                    (
                        str(updated.lease_expires_at),
                        str(current),
                        updated.owner,
                        str(updated.lease_token),
                        updated.generation,
                    ),
                )
            connection.commit()
            return updated
        except Exception:
            connection.rollback()
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
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_leader_lease WHERE scope='scheduler' FOR UPDATE"
                )
                row = cursor.fetchone()
                durable = None if row is None else _lease_from_row(row)
                if durable is None or not _same_generation(durable, lease):
                    raise SchedulerLeadershipLost("scheduler leadership lost")
                cursor.execute(
                    "UPDATE ronin_scheduler_leader_lease SET lease_expires_at=%s,updated_at=%s "
                    "WHERE scope='scheduler'",
                    (str(current), str(current)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _add_seconds(value: Instant | str, seconds: int) -> Instant:
    parsed = datetime.strptime(str(Instant(value)), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    return Instant((parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _lease_from_row(row: object) -> SchedulerLeaderLease:
    return SchedulerLeaderLease(
        owner=row["owner"],  # type: ignore[index]
        lease_token=LeaseToken(row["lease_token"]),  # type: ignore[index]
        generation=int(row["generation"]),  # type: ignore[index]
        acquired_at=Instant(row["acquired_at"]),  # type: ignore[index]
        lease_expires_at=Instant(row["lease_expires_at"]),  # type: ignore[index]
    )


def _same_generation(durable: SchedulerLeaderLease, lease: SchedulerLeaderLease) -> bool:
    return (
        durable.owner == lease.owner
        and durable.lease_token == lease.lease_token
        and durable.generation == lease.generation
    )


def _require_current(
    durable: SchedulerLeaderLease | None,
    lease: SchedulerLeaderLease,
    now: Instant,
) -> SchedulerLeaderLease:
    if durable is None:
        raise SchedulerLeadershipLost("scheduler leader lease does not exist")
    if not _same_generation(durable, lease) or durable.lease_expires_at <= now:
        raise SchedulerLeadershipLost("scheduler leadership lost")
    return durable


__all__ = ("PostgresSchedulerLeadershipStore",)
