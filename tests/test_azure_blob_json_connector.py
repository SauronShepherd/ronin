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
    class _PageIterator:
        def __init__(self, pages):
            self._pages = pages
            self._index = 0
            self.continuation_token = None

        def __iter__(self):
            return self

        def __next__(self):
            if self._index >= len(self._pages):
                self.continuation_token = None
                raise StopIteration
            self._index += 1
            self.continuation_token = str(self._index) if self._index < len(self._pages) else None
            return self._pages[self._index - 1]

    class _Listing:
        def __init__(self, pages):
            self._pages = pages

        def by_page(self, *, continuation_token=None, results_per_page=None):
            assert results_per_page == 1000
            start = int(continuation_token or "0")
            return _Container._PageIterator(self._pages[start:])

    def list_blobs(self, **_kwargs):
        return self._Listing([[type("Blob", (), {"name": "raw/events.json"})()]])

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


def test_azure_blob_discovery_is_page_bounded_and_rejects_oversized_page_size() -> None:
    container = _Container()
    connector = AzureBlobJsonConnector(container_client=container)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        connector.discover_page(_connection(), EnvironmentSecretResolver({}), page_size=1001)

    assets = connector.discover(_connection(), EnvironmentSecretResolver({}))
    assert [asset.handle.name for asset in assets] == ["events.json"]


def test_azure_blob_legacy_discover_stops_after_bounded_provider_requests() -> None:
    class _EndlessContainer(_Container):
        def __init__(self):
            self.listing = self._Listing([[] for _ in range(101)])

        def list_blobs(self, **_kwargs):
            return self.listing

    container = _EndlessContainer()
    connector = AzureBlobJsonConnector(container_client=container)
    with pytest.raises(ValueError, match="provider request limit"):
        connector.discover(_connection(), EnvironmentSecretResolver({}))


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
