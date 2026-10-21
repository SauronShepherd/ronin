from __future__ import annotations

import asyncio
from threading import Event

import pytest
from studio_storage import PostgresArtifactReferenceBarrier, postgres_retention_barrier


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[str, ...]) -> None:
        self.calls.append((statement, parameters))


class _Connection:
    def __init__(self) -> None:
        self.cursor_value = _Cursor()
        self.closed = False

    def cursor(self) -> _Cursor:
        return self.cursor_value

    def close(self) -> None:
        self.closed = True


class _Psycopg:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.calls: list[dict[str, object]] = []

    def connect(self, dsn: str, **kwargs: object) -> _Connection:
        self.calls.append({"dsn": dsn, **kwargs})
        return self.connection


@pytest.mark.parametrize(
    ("lease", "lock_function"),
    [("writer", "pg_advisory_lock_shared"), ("collector", "pg_advisory_lock")],
)
def test_barrier_uses_session_lock_and_always_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
    lease: str,
    lock_function: str,
) -> None:
    connection = _Connection()
    psycopg = _Psycopg(connection)
    monkeypatch.setattr(postgres_retention_barrier, "_psycopg", lambda: (psycopg, object()))
    barrier = PostgresArtifactReferenceBarrier("postgresql://db", application_name="test")

    with getattr(barrier, lease)():
        assert not connection.closed

    assert connection.closed
    assert psycopg.calls == [
        {"dsn": "postgresql://db", "autocommit": True, "application_name": "test"}
    ]
    assert connection.cursor_value.calls == [
        ("SELECT set_config('lock_timeout', %s, false)", ("30000ms",)),
        (
            f"SELECT {lock_function}(hashtext(%s),hashtext(%s))",
            ("ronin:artifact-retention", "global"),
        ),
    ]


def test_barrier_releases_session_when_protected_operation_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    psycopg = _Psycopg(connection)
    monkeypatch.setattr(postgres_retention_barrier, "_psycopg", lambda: (psycopg, object()))
    barrier = PostgresArtifactReferenceBarrier("postgresql://db")

    with pytest.raises(RuntimeError, match="write failed"), barrier.writer():
        raise RuntimeError("write failed")

    assert connection.closed


def test_async_writer_uses_shared_lock_and_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    psycopg = _Psycopg(connection)
    monkeypatch.setattr(postgres_retention_barrier, "_psycopg", lambda: (psycopg, object()))
    barrier = PostgresArtifactReferenceBarrier("postgresql://db")

    async def exercise() -> None:
        async with barrier.awriter():
            assert not connection.closed

    asyncio.run(exercise())

    assert connection.closed
    assert connection.cursor_value.calls[-1] == (
        "SELECT pg_advisory_lock_shared(hashtext(%s),hashtext(%s))",
        ("ronin:artifact-retention", "global"),
    )


def test_async_writer_cancellation_releases_lock_after_acquisition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    barrier = PostgresArtifactReferenceBarrier("postgresql://db")
    acquiring = Event()
    release_acquire = Event()

    def acquire(*, shared: bool) -> _Connection:
        assert shared
        acquiring.set()
        assert release_acquire.wait(timeout=5)
        return connection

    monkeypatch.setattr(barrier, "_acquire", acquire)

    async def exercise() -> None:
        lease = asyncio.create_task(use_barrier())
        assert await asyncio.to_thread(acquiring.wait, 5)
        lease.cancel()
        release_acquire.set()
        with pytest.raises(asyncio.CancelledError):
            await lease

    async def use_barrier() -> None:
        async with barrier.awriter():
            raise AssertionError("cancelled acquisition must not enter the lease")

    asyncio.run(exercise())
    assert connection.closed


@pytest.mark.parametrize(
    ("dsn", "application_name"),
    [
        ("", "ronin"),
        (" postgresql://db", "ronin"),
        ("postgresql://db", ""),
        ("postgresql://db", " ronin"),
    ],
)
def test_barrier_rejects_untrimmed_connection_configuration(
    dsn: str,
    application_name: str,
) -> None:
    with pytest.raises(ValueError, match="must be non-empty and trimmed"):
        PostgresArtifactReferenceBarrier(dsn, application_name=application_name)


@pytest.mark.parametrize("timeout", [0, 3_601, True, 1.5])
def test_barrier_rejects_invalid_lock_timeout(timeout: object) -> None:
    with pytest.raises(ValueError, match="lock_timeout_seconds"):
        PostgresArtifactReferenceBarrier("postgresql://db", lock_timeout_seconds=timeout)  # type: ignore[arg-type]
