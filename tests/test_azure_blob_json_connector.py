from __future__ import annotations

import pytest

from studio_connectors import AzureBlobJsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SourceCheckpoint
from studio_storage import EnvironmentSecretResolver


class _Downloader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def readall(self) -> bytes:
        return self.body


class _BlobClient:
    def download_blob(self, **_kwargs):
        return _Downloader(b'[{"id": 1}]')


class _Container:
    def list_blobs(self, **_kwargs):
        return [type("Blob", (), {"name": "raw/events.json"})()]

    def get_blob_client(self, _name):
        return _BlobClient()


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        ConnectionId("azure"),
        "Azure",
        "azure.blob.json",
        options=(("container", "data"), ("prefix", "raw")),
    )


def test_azure_blob_json_discovers_and_reads_snapshot() -> None:
    connector = AzureBlobJsonConnector(container_client=_Container())
    connection = _connection()
    secrets = EnvironmentSecretResolver({})
    asset = connector.discover(connection, secrets)[0].handle
    first = connector.read(connection, asset, secrets)
    second = connector.read(connection, asset, secrets, checkpoint=first.checkpoint)
    assert first.rows == ({"id": 1},)
    assert second.rows == ()


def test_azure_blob_json_rejects_cursor_checkpoint() -> None:
    with pytest.raises(ValueError, match="snapshot"):
        AzureBlobJsonConnector(container_client=_Container()).read(
            _connection(),
            AssetHandle(ConnectionId("azure"), ("raw",), "events.json"),
            EnvironmentSecretResolver({}),
            checkpoint=SourceCheckpoint("cursor", "x"),
        )


def test_azure_blob_rejects_persisted_credential_and_requires_secret_ref() -> None:
    with pytest.raises(ValueError, match="secret_refs"):
        ConnectionDefinition(
            ConnectionId("azure"),
            "Azure",
            "azure.blob.json",
            options=(
                ("container", "data"),
                ("account_url", "https://account.blob.core.windows.net"),
                ("credential", "plaintext-secret"),
            ),
        )
