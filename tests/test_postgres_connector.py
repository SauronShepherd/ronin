from __future__ import annotations

from types import SimpleNamespace

import pytest
from studio_connectors.postgres import PostgresConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SecretRef, SourceCheckpoint
from studio_storage import EnvironmentSecretResolver, PostgresMetadataStore


class _Cursor:
    description = (SimpleNamespace(name="id", type_code="int4"),)

    def execute(self, query: object, params: object = ()) -> None:
        self.query = query
        self.params = params

    def fetchall(self) -> list[tuple[int]]:
        return [(1,)]

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Database:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_instance

    def __enter__(self) -> _Database:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _ReadyDatabase:
    def __init__(self, result: object = (1,)) -> None:
        self.result = result

    def cursor(self) -> _ReadyDatabase:
        return self

    def execute(self, _query: str) -> None:
        return None

    def fetchone(self) -> object:
        return self.result

    def close(self) -> None:
        return None

    def __enter__(self) -> _ReadyDatabase:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Sql:
    class _Statement:
        def __init__(self, text: str) -> None:
            self.text = text

        def format(self, *_args: object) -> _Sql._Statement:
            values = tuple(str(value) for value in _args)
            return _Sql._Statement(self.text.format(*values))

        def join(self, parts: object) -> _Sql._Statement:
            return _Sql._Statement(self.text.join(str(part) for part in parts))

        def __add__(self, other: _Sql._Statement) -> _Sql._Statement:
            return _Sql._Statement(self.text + other.text)

        def __str__(self) -> str:
            return self.text

    def SQL(self, _value: str) -> _Sql._Statement:
        return self._Statement(_value)

    def Identifier(self, value: str) -> str:
        return '"' + value.replace('"', '""') + '"'


class _PagedCursor:
    def __init__(self) -> None:
        self.rows: list[tuple[object, ...]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> None:
        if "SELECT DISTINCT table_schema, table_name" in query:
            tables = [("public", "alpha"), ("public", "bravo"), ("public", "charlie")]
            if len(params) == 3:
                after = (str(params[0]), str(params[1]))
                tables = [table for table in tables if table > after]
            self.rows = tables[: int(params[-1])]
        else:
            self.rows = [
                (str(params[index]), str(params[index + 1]), "id", "integer", "NO")
                for index in range(0, len(params), 2)
            ]

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def __enter__(self) -> _PagedCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _PagedDatabase:
    def __init__(self) -> None:
        self.cursor_instance = _PagedCursor()

    def cursor(self) -> _PagedCursor:
        return self.cursor_instance

    def __enter__(self) -> _PagedDatabase:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        ConnectionId("pg"),
        "PostgreSQL",
        "postgresql",
        options=(("host", "localhost"), ("database", "ronin")),
        secret_refs=(
            ("user", SecretRef("secret://env/PGUSER")),
            ("password", SecretRef("secret://env/PGPASSWORD")),
        ),
    )


def test_postgres_snapshot_checkpoint_suppresses_unchanged_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _Database()
    monkeypatch.setattr(
        "studio_connectors.postgres._psycopg",
        lambda: (SimpleNamespace(connect=lambda **_kwargs: database), _Sql()),
    )
    connector = PostgresConnector()
    connection = _connection()
    asset = AssetHandle(connection.id, ("public",), "events")
    secrets = EnvironmentSecretResolver({"PGUSER": "ronin", "PGPASSWORD": "secret"})

    first = connector.read(connection, asset, secrets)
    second = connector.read(connection, asset, secrets, checkpoint=first.checkpoint)

    assert len(first.rows) == 1
    assert second.rows == ()
    assert second.checkpoint == first.checkpoint


def test_postgres_rejects_unsupported_checkpoint() -> None:
    with pytest.raises(ValueError, match="snapshot or watermark"):
        PostgresConnector().read(
            _connection(),
            AssetHandle(ConnectionId("pg"), ("public",), "events"),
            EnvironmentSecretResolver({"PGUSER": "ronin", "PGPASSWORD": "secret"}),
            checkpoint=SourceCheckpoint("cursor", "x"),
        )


def test_postgres_descriptor_advertises_schema_discovery() -> None:
    capabilities = PostgresConnector.descriptor.capabilities
    assert capabilities.discover is True
    assert capabilities.schema is True
    assert capabilities.incremental is True
    assert "integer" in capabilities.watermark_types
    assert capabilities.max_page_size == 10_000


def test_postgres_watermark_checkpoint_round_trips_typed_values() -> None:
    from datetime import UTC, date, datetime
    from decimal import Decimal
    from uuid import UUID

    from studio_connectors.postgres import PostgresWatermarkCheckpoint

    checkpoint = PostgresWatermarkCheckpoint(
        "pg",
        ("public",),
        "events",
        "observed_at",
        ("id",),
        (datetime(2026, 1, 2, tzinfo=UTC), 2**62),
        "a" * 64,
        True,
    )
    decoded = PostgresWatermarkCheckpoint.decode(checkpoint.encode())
    assert decoded == checkpoint
    assert PostgresWatermarkCheckpoint.decode(
        PostgresWatermarkCheckpoint(
            "pg", ("public",), "events", "day", ("id",), (date(2026, 1, 2), 1), "b" * 64, True
        ).encode()
    ).values == (date(2026, 1, 2), 1)
    assert PostgresWatermarkCheckpoint.decode(
        PostgresWatermarkCheckpoint(
            "pg",
            ("public",),
            "events",
            "amount",
            ("id",),
            (Decimal("1.25"), UUID(int=1)),
            "c" * 64,
            True,
        ).encode()
    ).values == (Decimal("1.25"), UUID(int=1))
    with pytest.raises(ValueError, match="schema fingerprint"):
        PostgresWatermarkCheckpoint(
            "pg", ("public",), "events", "updated_at", ("id",), (), "invalid", False
        )


def test_postgres_incremental_read_uses_bounded_composite_watermark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studio_connectors.postgres import PostgresWatermarkCheckpoint

    class Cursor:
        description = (
            SimpleNamespace(name="updated_at", type_code="int8"),
            SimpleNamespace(name="id", type_code="int8"),
        )

        def __init__(self, rows: list[tuple[int, int]]) -> None:
            self.rows = rows
            self.executions: list[tuple[str, object]] = []

        def execute(self, query: object, params: object = ()) -> None:
            self.query, self.params = str(query), params
            self.executions.append((self.query, params))

        def fetchall(self) -> list[tuple[object, ...]]:
            if "pg_catalog.pg_index" in self.query:
                return [(("id",),)]
            return self.rows

        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Database:
        def __init__(self, rows: list[tuple[int, int]]) -> None:
            self.cursor_instance = Cursor(rows)

        def cursor(self) -> Cursor:
            return self.cursor_instance

        def __enter__(self) -> Database:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    first_database = Database([(1, 1), (2, 1), (2, 2)])
    monkeypatch.setattr(
        "studio_connectors.postgres._psycopg",
        lambda: (SimpleNamespace(connect=lambda **_kwargs: first_database), _Sql()),
    )
    connection = ConnectionDefinition(
        ConnectionId("pg"),
        "PostgreSQL",
        "postgresql",
        options=(
            ("database", "ronin"),
            ("host", "localhost"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
        secret_refs=_connection().secret_refs,
    )
    asset = AssetHandle(connection.id, ("public",), "events")
    secrets = EnvironmentSecretResolver({"PGUSER": "ronin", "PGPASSWORD": "secret"})
    first = PostgresConnector().read(connection, asset, secrets, limit=2)

    assert [row["id"] for row in first.rows] == [1, 1]
    assert first.has_more is True
    assert first_database.cursor_instance.executions[0][1] == ("public", "events")
    assert first_database.cursor_instance.params == (3,)
    assert 'ORDER BY "updated_at", "id"' in first_database.cursor_instance.query
    saved = PostgresWatermarkCheckpoint.decode(first.checkpoint.value)
    assert saved.values == (2, 1)

    second_database = Database([(2, 2)])
    monkeypatch.setattr(
        "studio_connectors.postgres._psycopg",
        lambda: (SimpleNamespace(connect=lambda **_kwargs: second_database), _Sql()),
    )
    second = PostgresConnector().read(
        connection, asset, secrets, limit=2, checkpoint=first.checkpoint
    )
    assert [row["id"] for row in second.rows] == [2]
    assert second.has_more is False
    assert second_database.cursor_instance.params == (2, 2, 1, 3)
    assert " OR " in second_database.cursor_instance.query
    assert PostgresWatermarkCheckpoint.decode(second.checkpoint.value).values == (2, 2)


def test_postgres_watermark_rejects_invalid_columns_nulls_and_source_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studio_connectors.postgres import PostgresWatermarkCheckpoint

    connection = ConnectionDefinition(
        ConnectionId("pg"),
        "PostgreSQL",
        "postgresql",
        options=(
            ("database", "ronin"),
            ("host", "localhost"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
        secret_refs=_connection().secret_refs,
    )
    secrets = EnvironmentSecretResolver({"PGUSER": "ronin", "PGPASSWORD": "secret"})
    asset = AssetHandle(connection.id, ("public",), "events")
    invalid = ConnectionDefinition(
        ConnectionId("pg"),
        "PostgreSQL",
        "postgresql",
        options=(
            ("database", "ronin"),
            ("host", "localhost"),
            ("incremental_column", "updated_at"),
        ),
        secret_refs=_connection().secret_refs,
    )
    with pytest.raises(ValueError, match="tie_breaker_columns"):
        PostgresConnector().read(invalid, asset, secrets)
    invalid_column = ConnectionDefinition(
        ConnectionId("pg"),
        "PostgreSQL",
        "postgresql",
        options=(
            ("database", "ronin"),
            ("host", "localhost"),
            ("incremental_column", "updated_at; DROP TABLE events"),
            ("tie_breaker_columns", "id"),
        ),
        secret_refs=_connection().secret_refs,
    )
    with pytest.raises(ValueError, match="simple SQL identifier"):
        PostgresConnector().read(invalid_column, asset, secrets)

    class NullCursor:
        description = (
            SimpleNamespace(name="updated_at", type_code="int8"),
            SimpleNamespace(name="id", type_code="int8"),
        )

        def execute(self, *_args: object) -> None:
            self.query = str(_args[0])

        def fetchall(self) -> list[tuple[object, object]]:
            if "pg_catalog.pg_index" in self.query:
                return [(("id",),)]
            return [(1, None)]

        def __enter__(self) -> NullCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class NullDatabase:
        def cursor(self) -> NullCursor:
            return NullCursor()

        def __enter__(self) -> NullDatabase:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        "studio_connectors.postgres._psycopg",
        lambda: (SimpleNamespace(connect=lambda **_kwargs: NullDatabase()), _Sql()),
    )
    with pytest.raises(ValueError, match="must not be null"):
        PostgresConnector().read(connection, asset, secrets)

    class NonUniqueCursor(NullCursor):
        def fetchall(self) -> list[tuple[object, object]]:
            return [] if "pg_catalog.pg_index" in self.query else [(1, 1)]

    class NonUniqueDatabase(NullDatabase):
        def cursor(self) -> NonUniqueCursor:
            return NonUniqueCursor()

    monkeypatch.setattr(
        "studio_connectors.postgres._psycopg",
        lambda: (SimpleNamespace(connect=lambda **_kwargs: NonUniqueDatabase()), _Sql()),
    )
    with pytest.raises(ValueError, match="must contain a non-partial unique key"):
        PostgresConnector().read(connection, asset, secrets)

    foreign = PostgresWatermarkCheckpoint(
        "another-connection", ("public",), "events", "updated_at", ("id",), (1, 1), "a" * 64, True
    )
    with pytest.raises(ValueError, match="another source"):
        PostgresConnector().read(
            connection, asset, secrets, checkpoint=SourceCheckpoint("watermark", foreign.encode())
        )


def test_postgres_table_discovery_uses_keyset_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _PagedDatabase()
    monkeypatch.setattr(
        "studio_connectors.postgres._psycopg",
        lambda: (SimpleNamespace(connect=lambda **_kwargs: database), _Sql()),
    )
    connector = PostgresConnector()
    connection = _connection()
    secrets = EnvironmentSecretResolver({"PGUSER": "ronin", "PGPASSWORD": "secret"})

    first = connector.discover_page(connection, secrets, page_size=1)
    second = connector.discover_page(connection, secrets, cursor=first.next_cursor, page_size=1)
    third = connector.discover_page(connection, secrets, cursor=second.next_cursor, page_size=1)

    assert [item.handle.name for item in first.items] == ["alpha"]
    assert first.truncated
    assert first.next_cursor is not None
    assert [item.handle.name for item in second.items] == ["bravo"]
    assert second.truncated
    assert second.next_cursor is not None
    assert [item.handle.name for item in third.items] == ["charlie"]
    assert not third.truncated
    assert third.next_cursor is None
    assert first.items[0].fields[0].name == "id"


def test_postgres_discovery_rejects_invalid_cursor() -> None:
    with pytest.raises(ValueError, match="cursor is invalid"):
        PostgresConnector()._decode_discovery_cursor("***")  # noqa: SLF001


def test_postgres_metadata_readiness_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    store = PostgresMetadataStore.__new__(PostgresMetadataStore)
    database = _ReadyDatabase()
    monkeypatch.setattr(store, "_connect", lambda: database)
    assert store.ready()

    def unavailable() -> _ReadyDatabase:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(store, "_connect", unavailable)
    assert not store.ready()
