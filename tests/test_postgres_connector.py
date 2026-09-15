from __future__ import annotations

from types import SimpleNamespace

import pytest
from studio_connectors.postgres import PostgresConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SecretRef, SourceCheckpoint
from studio_storage import EnvironmentSecretResolver


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


class _Sql:
    class _Statement:
        def format(self, *args: object) -> _Statement:
            return self

    def SQL(self, value: str) -> _Statement:
        return self._Statement()

    def Identifier(self, value: str) -> str:
        return value


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
        lambda: (SimpleNamespace(connect=lambda **kwargs: database), _Sql()),
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
