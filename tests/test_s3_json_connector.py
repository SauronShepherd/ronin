from __future__ import annotations

import pytest
from studio_connectors import S3JsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SourceCheckpoint
from studio_storage import EnvironmentSecretResolver


class _Body:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self, limit: int) -> bytes:
        return self.value[:limit]


class _S3:
    def list_objects_v2(self, **_kwargs):
        return {"Contents": [{"Key": "raw/events.json"}, {"Key": "raw/readme.txt"}]}

    def get_object(self, **_kwargs):
        return {"Body": _Body(b'[{"id": 1}]')}


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        ConnectionId("s3"), "S3", "s3.json", options=(("bucket", "data"), ("prefix", "raw"))
    )


def test_s3_json_discovers_and_snapshot_reads() -> None:
    connector = S3JsonConnector(client=_S3())
    connection = _connection()
    assets = connector.discover(connection, EnvironmentSecretResolver({}))
    assert [asset.handle.name for asset in assets] == ["events.json"]
    result = connector.read(connection, assets[0].handle, EnvironmentSecretResolver({}))
    unchanged = connector.read(
        connection, assets[0].handle, EnvironmentSecretResolver({}), checkpoint=result.checkpoint
    )
    assert result.rows == ({"id": 1},)
    assert unchanged.rows == ()


def test_s3_json_rejects_unsafe_prefix_and_checkpoint() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        S3JsonConnector(client=_S3()).discover(
            ConnectionDefinition(
                ConnectionId("s3"),
                "S3",
                "s3.json",
                options=(("bucket", "data"), ("prefix", "../raw")),
            ),
            EnvironmentSecretResolver({}),
        )
    with pytest.raises(ValueError, match="snapshot"):
        S3JsonConnector(client=_S3()).read(
            _connection(),
            AssetHandle(ConnectionId("s3"), ("raw",), "events.json"),
            EnvironmentSecretResolver({}),
            checkpoint=SourceCheckpoint("cursor", "x"),
        )
