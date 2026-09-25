from __future__ import annotations

import pytest

from studio_connectors import (
    JdbcBridgeProvenance,
    JdbcConnector,
    JdbcDependencyError,
    JdbcIncrementalCheckpointV2,
)
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SourceCheckpoint
from studio_storage import EnvironmentSecretResolver


class _Cursor:
    description = (("id", "integer"),)

    def execute(self, query, params=()):
        self.query, self.params = query, params

    def fetchall(self):
        return [(1,)]


class _Db:
    def cursor(self):
        return _Cursor()

    def close(self):
        pass


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        ConnectionId("jdbc"), "JDBC", "jdbc", options=(("url", "jdbc:test"),)
    )


def test_jdbc_bridge_supports_discovery_and_snapshot_read() -> None:
    connector = JdbcConnector(connect=lambda *_args: _Db())
    connection = _connection()
    secrets = EnvironmentSecretResolver({})
    assets = connector.discover(connection, secrets)
    assert assets[0].handle.name == "1"
    result = connector.read(connection, AssetHandle(connection.id, ("public",), "events"), secrets)
    assert result.rows == ({"id": 1},)


def test_jdbc_without_bridge_fails_closed() -> None:
    with pytest.raises(JdbcDependencyError, match="bridge"):
        JdbcConnector().discover(_connection(), EnvironmentSecretResolver({}))


def test_jdbc_discovery_validates_and_applies_row_limit() -> None:
    connector = JdbcConnector(connect=lambda *_args: _Db())
    with pytest.raises(ValueError, match="discovery limit"):
        connector.discover(_connection(), EnvironmentSecretResolver({}), limit=0)
    connector.discover(_connection(), EnvironmentSecretResolver({}), limit=7)


def test_jdbc_discovery_page_is_bounded_and_returns_opaque_cursor() -> None:
    connector = JdbcConnector(connect=lambda *_args: _Db())
    page = connector.discover_page(_connection(), EnvironmentSecretResolver({}), page_size=1)
    assert len(page.items) == 1
    assert page.truncated is True
    assert page.next_cursor == "1"


def test_jdbc_incremental_watermark_is_ordered_and_advanced() -> None:
    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(("url", "jdbc:test"), ("incremental_column", "id")),
    )
    connector = JdbcConnector(connect=lambda *_args: _Db())
    result = connector.read(
        connection,
        AssetHandle(connection.id, ("public",), "events"),
        EnvironmentSecretResolver({}),
        checkpoint=SourceCheckpoint("watermark", "0"),
    )
    assert result.checkpoint == SourceCheckpoint("watermark", "1")


def test_jdbc_v2_checkpoint_round_trip_preserves_typed_cursor() -> None:
    checkpoint = JdbcIncrementalCheckpointV2(
        "asset-1", "updated_at", 1735689600, ("id",), (42,), "schema-hash", 3
    )
    assert JdbcIncrementalCheckpointV2.decode(checkpoint.encode()) == checkpoint
    assert checkpoint.predicate() == (
        '(("updated_at" > ?) OR ("updated_at" = ? AND "id" > ?))',
        (1735689600, 1735689600, 42),
    )
    assert checkpoint.order_by() == '"updated_at", "id"'


def test_jdbc_v2_read_binds_lexicographic_cursor() -> None:
    class Cursor(_Cursor):
        description = (("updated_at", "integer"), ("id", "integer"))

        def fetchall(self):
            return [(10, 8)]

    class Database(_Db):
        def cursor(self):
            return Cursor()

    checkpoint = JdbcIncrementalCheckpointV2(
        "public.events", "updated_at", 10, ("id",), (7,), "schema", 1
    )
    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    connector = JdbcConnector(connect=lambda *_args: Database())
    result = connector.read(
        connection,
        AssetHandle(connection.id, ("public",), "events"),
        EnvironmentSecretResolver({}),
        checkpoint=SourceCheckpoint("watermark", checkpoint.encode()),
    )
    assert result.rows == ({"updated_at": 10, "id": 8},)


def test_jdbc_v2_empty_source_does_not_create_empty_string_cursor() -> None:
    class EmptyCursor(_Cursor):
        description = (("updated_at", "timestamp"), ("id", "integer"))

        def fetchall(self):
            return []

    class EmptyDatabase(_Db):
        def cursor(self):
            return EmptyCursor()

    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    result = JdbcConnector(connect=lambda *_args: EmptyDatabase()).read(
        connection,
        AssetHandle(connection.id, ("public",), "events"),
        EnvironmentSecretResolver({}),
    )
    decoded = JdbcIncrementalCheckpointV2.decode(result.checkpoint.value)
    assert decoded.incremental_value is None
    assert decoded.incremental_value != ""


def test_jdbc_bridge_provenance_is_explicit_and_fail_closed() -> None:
    connector = JdbcConnector(
        connect=lambda _connection, _secrets: object(),
        provenance=JdbcBridgeProvenance("bridge-1", "sqlite-jdbc", "3.45.0"),
    )
    assert connector.bridge_provenance().driver_name == "sqlite-jdbc"
    with pytest.raises(JdbcDependencyError):
        JdbcConnector(connect=lambda _connection, _secrets: object()).bridge_provenance()
