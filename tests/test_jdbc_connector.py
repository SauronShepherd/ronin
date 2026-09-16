from __future__ import annotations

import pytest
from studio_connectors import JdbcConnector, JdbcDependencyError, JdbcIncrementalCheckpointV2
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
