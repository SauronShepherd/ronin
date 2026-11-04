from __future__ import annotations

from types import SimpleNamespace

import pytest
import studio_connectors.azure_blob_json as azure_blob_json
from studio_connectors import AzureBlobJsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SecretRef, SourceCheckpoint
from studio_storage import EnvironmentSecretResolver


class _Downloader:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def chunks(self):
        yield self.body


class _BlobClient:
    body = b'[ {"id": 1} ]'
    download_options: dict[str, object] = {}

    def get_blob_properties(self):
        return SimpleNamespace(size=len(self.body), etag='"test-etag"')

    def download_blob(self, **_kwargs):
        self.download_options = _kwargs
        return _Downloader(self.body)


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
            assert results_per_page is None
            start = int(continuation_token or "0")
            return _Container._PageIterator(self._pages[start:])

    def list_blobs(self, *, results_per_page=None, **_kwargs):
        assert results_per_page == 1000
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


@pytest.fixture(autouse=True)
def _stub_azure_match_condition(monkeypatch: pytest.MonkeyPatch) -> None:
    def condition() -> str:
        return "if-not-modified"

    monkeypatch.setattr(azure_blob_json, "_if_not_modified_match_condition", condition)


def test_azure_blob_json_discovers_and_reads_snapshot() -> None:
    connector = AzureBlobJsonConnector(container_client=_Container())
    connection = _connection()
    secrets = EnvironmentSecretResolver({})
    asset = connector.discover(connection, secrets)[0].handle
    first = connector.read(connection, asset, secrets)
    second = connector.read(connection, asset, secrets, checkpoint=first.checkpoint)
    assert first.rows == ({"id": 1},)
    assert second.rows == ()


def test_azure_blob_read_binds_download_to_etag_and_streams_chunks() -> None:
    blob = _BlobClient()
    container = _Container()
    container.get_blob_client = lambda _name: blob
    connector = AzureBlobJsonConnector(container_client=container)
    connector.read(
        _connection(),
        AssetHandle(ConnectionId("azure"), ("raw",), "events.json"),
        EnvironmentSecretResolver({}),
    )
    assert blob.download_options["etag"] == '"test-etag"'
    assert blob.download_options["match_condition"] == "if-not-modified"
    assert "max_concurrency" in blob.download_options


def test_azure_blob_rejects_oversized_object_before_download() -> None:
    class OversizedBlob(_BlobClient):
        def get_blob_properties(self):
            return SimpleNamespace(size=AzureBlobJsonConnector.MAX_BLOB_BYTES + 1, etag='"large"')

        def download_blob(self, **_kwargs):
            raise AssertionError("oversized blob must not be downloaded")

    container = _Container()
    container.get_blob_client = lambda _name: OversizedBlob()
    with pytest.raises(ValueError, match="byte limit"):
        AzureBlobJsonConnector(container_client=container).read(
            _connection(),
            AssetHandle(ConnectionId("azure"), ("raw",), "events.json"),
            EnvironmentSecretResolver({}),
        )


def test_azure_blob_rejects_size_growth_during_streamed_download() -> None:
    class GrowingBlob(_BlobClient):
        body = b'{"id":1}'

        def get_blob_properties(self):
            return SimpleNamespace(size=1, etag='"before"')

    container = _Container()
    container.get_blob_client = lambda _name: GrowingBlob()
    with pytest.raises(ValueError, match="byte limit"):
        AzureBlobJsonConnector(container_client=container).read(
            _connection(),
            AssetHandle(ConnectionId("azure"), ("raw",), "events.json"),
            EnvironmentSecretResolver({}),
        )


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

        def list_blobs(self, *, results_per_page=None, **_kwargs):
            assert results_per_page == 1000
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


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_azure_blob_allows_explicit_loopback_http_emulator_only(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, str | None]] = []

    class Service:
        def __init__(
            self,
            *,
            account_url: str,
            credential: str,
            api_version: str | None = None,
        ) -> None:
            calls.append((account_url, credential, api_version))

        def get_container_client(self, container: str) -> object:
            return container

    monkeypatch.setattr(azure_blob_json, "_azure", lambda: Service)
    connection = ConnectionDefinition(
        ConnectionId("azure-local"),
        "Azure local emulator",
        "azure.blob.json",
        options=(
            ("account_url", f"http://{host}:10000/devstoreaccount1"),
            ("api_version", "2025-11-05"),
            ("allow_local_http", "true"),
            ("container", "data"),
        ),
        secret_refs=(("credential", SecretRef("secret://env/AZURITE_KEY")),),
    )
    client = AzureBlobJsonConnector()._container_client(
        connection, EnvironmentSecretResolver({"AZURITE_KEY": "local-test-key"})
    )

    assert client == "data"
    assert calls == [(f"http://{host}:10000/devstoreaccount1", "local-test-key", "2025-11-05")]


@pytest.mark.parametrize(
    ("account_url", "allow_local_http"),
    [
        ("http://storage.example.test/devstoreaccount1", "true"),
        ("http://127.0.0.1:10000/devstoreaccount1", "false"),
    ],
)
def test_azure_blob_rejects_plaintext_http_outside_explicit_loopback(
    account_url: str,
    allow_local_http: str,
) -> None:
    connection = ConnectionDefinition(
        ConnectionId("azure-local"),
        "Azure endpoint",
        "azure.blob.json",
        options=(
            ("account_url", account_url),
            ("allow_local_http", allow_local_http),
            ("container", "data"),
        ),
        secret_refs=(("credential", SecretRef("secret://env/AZURITE_KEY")),),
    )
    with pytest.raises(ValueError, match="loopback emulator"):
        AzureBlobJsonConnector()._container_client(
            connection, EnvironmentSecretResolver({"AZURITE_KEY": "local-test-key"})
        )
