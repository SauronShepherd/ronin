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
        def format(self, *_args: object) -> _Sql._Statement:
            return self

    def SQL(self, _value: str) -> _Sql._Statement:
        return self._Statement()

    def Identifier(self, value: str) -> str:
        return value


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


def test_postgres_rejects_non_snapshot_checkpoint() -> None:
    with pytest.raises(ValueError, match="snapshot checkpoints"):
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
    assert capabilities.incremental is False
    assert capabilities.max_page_size == 10_000


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
