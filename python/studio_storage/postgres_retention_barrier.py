"""Cross-process barrier for artifact reference writes and garbage collection.

The barrier is an opt-in coordination primitive. Every artifact producer must
hold ``writer()`` from before writing bytes through committing its reference;
the collector must hold ``collector()`` across reference discovery and deletion.
Until all producers participate, automated cleanup must remain disabled.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from .postgres_core import _psycopg

_LOCK_NAMESPACE = "ronin:artifact-retention"
_LOCK_SCOPE = "global"


class PostgresArtifactReferenceBarrier:
    """Use PostgreSQL session advisory locks to serialize writers with collection.

    Writer leases share a lock, so independent producers can proceed together.
    A collector takes the exclusive form and therefore waits for every current
    writer while preventing new ones from publishing references. Session locks
    are held on a dedicated connection and are released if the process exits.
    """

    def __init__(
        self,
        dsn: str,
        *,
        application_name: str = "ronin-artifact-retention",
        lock_timeout_seconds: int = 30,
    ) -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        if not application_name or application_name != application_name.strip():
            raise ValueError("application_name must be non-empty and trimmed")
        if (
            not isinstance(lock_timeout_seconds, int)
            or isinstance(lock_timeout_seconds, bool)
            or not 1 <= lock_timeout_seconds <= 3_600
        ):
            raise ValueError("lock_timeout_seconds must be an integer between 1 and 3600")
        self._dsn = dsn
        self._application_name = application_name
        self._lock_timeout_seconds = lock_timeout_seconds

    @contextmanager
    def writer(self) -> Iterator[None]:
        """Protect artifact materialization through durable reference commit."""
        with self._lease(shared=True):
            yield

    @contextmanager
    def collector(self) -> Iterator[None]:
        """Protect a complete reference snapshot, inventory scan, and deletion."""
        with self._lease(shared=False):
            yield

    @contextmanager
    def _lease(self, *, shared: bool) -> Iterator[None]:
        connection = self._acquire(shared=shared)
        try:
            yield
        finally:
            # Closing a session releases its advisory lock, including when the
            # protected operation raises.
            connection.close()

    @asynccontextmanager
    async def awriter(self) -> AsyncIterator[None]:
        """Acquire and release a writer lease without blocking an async loop."""
        acquire = asyncio.create_task(asyncio.to_thread(self._acquire, shared=True))
        try:
            connection = await asyncio.shield(acquire)
        except asyncio.CancelledError:
            # The thread cannot be cancelled. Join it and release any lock it
            # acquired before propagating cancellation to avoid leaking a session.
            try:
                connection = await acquire
            except BaseException:
                raise
            close = asyncio.create_task(asyncio.to_thread(connection.close))
            await asyncio.shield(close)
            raise
        try:
            yield
        finally:
            close = asyncio.create_task(asyncio.to_thread(connection.close))
            try:
                await asyncio.shield(close)
            except asyncio.CancelledError:
                await close
                raise

    def _acquire(self, *, shared: bool) -> Any:
        psycopg, _ = _psycopg()
        connection = psycopg.connect(
            self._dsn,
            autocommit=True,
            application_name=self._application_name,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('lock_timeout', %s, false)",
                    (f"{self._lock_timeout_seconds * 1_000}ms",),
                )
                operation = "pg_advisory_lock_shared" if shared else "pg_advisory_lock"
                cursor.execute(
                    f"SELECT {operation}(hashtext(%s),hashtext(%s))",
                    (_LOCK_NAMESPACE, _LOCK_SCOPE),
                )
            return connection
        except BaseException:
            connection.close()
            raise


__all__ = ("PostgresArtifactReferenceBarrier",)
