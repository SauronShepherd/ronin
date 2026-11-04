"""Bounded Azure Blob Storage JSON/JSONL source connector."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectorCapabilities,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
)
from studio_storage.secrets import SecretResolver

from .contracts import ConnectorReadResult, DiscoveryPage


def _azure() -> Any:
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Azure Blob JSON connector requires azure-storage-blob") from exc
    return BlobServiceClient


def _if_not_modified_match_condition() -> Any:
    try:
        from azure.core import MatchConditions
    except ImportError as exc:  # pragma: no cover - Azure SDK extra is optional
        raise RuntimeError("Azure Blob JSON connector requires azure-core") from exc
    return MatchConditions.IfNotModified


class AzureBlobJsonConnector:
    """Discover and read JSON or JSONL blobs from an Azure container."""

    MAX_BLOB_BYTES = 10 * 1024 * 1024
    MAX_PAGE_SIZE = 1_000
    MAX_DISCOVERY_PAGES = 100
    MAX_DISCOVERED_ASSETS = 10_000

    descriptor = ConnectorDescriptor(
        "azure.blob.json",
        1,
        ConnectorCapabilities(discover=True, read=True, max_page_size=MAX_PAGE_SIZE),
    )

    def __init__(self, *, container_client: Any | None = None) -> None:
        self._container = container_client

    def _config(self, connection: ConnectionDefinition) -> tuple[str, str]:
        if connection.connector_id != self.descriptor.connector_id:
            raise ValueError("connection does not target the Azure Blob JSON connector")
        options = dict(connection.options)
        container = options.get("container", "").strip()
        prefix = options.get("prefix", "").strip()
        if not container or "/" in container or ".." in container:
            raise ValueError("Azure container must be a safe non-empty name")
        if ".." in prefix.split("/"):
            raise ValueError("Azure prefix contains unsafe path components")
        return container, prefix

    def _container_client(self, connection: ConnectionDefinition, secrets: SecretResolver) -> Any:
        if self._container is not None:
            return self._container
        options = dict(connection.options)
        account_url = options.get("account_url", "").strip()
        parsed = urlsplit(account_url)
        local_host = False
        if parsed.hostname:
            try:
                local_host = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                local_host = parsed.hostname.casefold().rstrip(".") == "localhost"
        local_http = (
            parsed.scheme == "http"
            and local_host
            and options.get("allow_local_http", "false").casefold() == "true"
        )
        credential_ref = dict(connection.secret_refs).get("credential")
        api_version = options.get("api_version")
        if api_version is not None:
            try:
                valid_api_version = date.fromisoformat(api_version).isoformat() == api_version
            except ValueError:
                valid_api_version = False
            if not valid_api_version:
                raise ValueError("Azure Blob api_version must be a YYYY-MM-DD date")
        if (
            (parsed.scheme != "https" and not local_http)
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or credential_ref is None
        ):
            raise ValueError(
                "Azure Blob requires a clean HTTPS account_url and credential secret-ref; "
                "HTTP is allowed only for an explicitly enabled loopback emulator"
            )
        credential = secrets.resolve(credential_ref).reveal_text()
        client_options: dict[str, object] = {
            "account_url": account_url,
            "credential": credential,
        }
        if api_version is not None:
            client_options["api_version"] = api_version
        return _azure()(**client_options).get_container_client(self._config(connection)[0])

    def discover(
        self, connection: ConnectionDefinition, secrets: SecretResolver
    ) -> tuple[DiscoveredAsset, ...]:
        _, prefix = self._config(connection)
        listing = self._container_client(connection, secrets).list_blobs(
            name_starts_with=prefix, results_per_page=self.MAX_PAGE_SIZE
        )
        if not hasattr(listing, "by_page"):
            raise RuntimeError("Azure Blob listing does not expose paginated iteration")
        pages = listing.by_page()
        page_iterator = iter(pages)
        assets: list[DiscoveredAsset] = []
        for page_number in range(1, self.MAX_DISCOVERY_PAGES + 1):
            try:
                page = tuple(next(page_iterator))
            except StopIteration:
                break
            if len(page) > self.MAX_PAGE_SIZE:
                raise ValueError(
                    "Azure Blob provider returned more blobs than the requested page size"
                )
            for blob in page:
                name = str(blob.name)
                if name.lower().endswith((".json", ".jsonl")):
                    parts = tuple(part for part in name.split("/") if part)
                    assets.append(
                        DiscoveredAsset(
                            AssetHandle(connection.id, parts[:-1], parts[-1]), "blob", ()
                        )
                    )
            if len(assets) > self.MAX_DISCOVERED_ASSETS:
                raise ValueError(
                    "Azure Blob discovery exceeded the asset limit; "
                    "use paginated connector discovery"
                )
            if not getattr(pages, "continuation_token", None):
                break
            if page_number == self.MAX_DISCOVERY_PAGES:
                raise ValueError(
                    "Azure Blob discovery exceeded the provider request limit; "
                    "use paginated connector discovery"
                )
        return tuple(sorted(assets, key=lambda item: item.handle.qualified_name))

    def discover_page(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
        *,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> DiscoveryPage[DiscoveredAsset]:
        """Discover one bounded Azure page using the SDK's opaque continuation token."""
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or page_size < 1
            or page_size > self.MAX_PAGE_SIZE
        ):
            raise ValueError(
                f"Azure discovery page_size must be between 1 and {self.MAX_PAGE_SIZE}"
            )
        _, prefix = self._config(connection)
        listing = self._container_client(connection, secrets).list_blobs(
            name_starts_with=prefix, results_per_page=page_size
        )
        if not hasattr(listing, "by_page"):
            raise RuntimeError("Azure Blob listing does not expose paginated iteration")
        pages = listing.by_page(continuation_token=cursor)
        iterator = iter(pages)
        try:
            page = tuple(next(iterator))
        except StopIteration:
            return DiscoveryPage((), None, False)
        next_cursor = getattr(pages, "continuation_token", None)
        assets = []
        for blob in page:
            name = str(blob.name)
            if name.lower().endswith((".json", ".jsonl")):
                parts = tuple(part for part in name.split("/") if part)
                assets.append(
                    DiscoveredAsset(AssetHandle(connection.id, parts[:-1], parts[-1]), "blob", ())
                )
        if len(page) > page_size:
            raise ValueError("Azure Blob provider returned more blobs than the requested page size")
        truncated = bool(next_cursor)
        return DiscoveryPage(
            tuple(sorted(assets, key=lambda item: item.handle.qualified_name)),
            next_cursor if truncated else None,
            truncated,
        )

    def read(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        secrets: SecretResolver,
        *,
        limit: int = 10_000,
        checkpoint: SourceCheckpoint | None = None,
    ) -> ConnectorReadResult:
        if checkpoint is not None and checkpoint.strategy != "snapshot":
            raise ValueError("Azure Blob JSON connector only supports snapshot checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("Azure Blob read limit must be between 1 and 100000")
        if asset.connection_id != connection.id:
            raise ValueError("Azure Blob asset handle does not belong to the connection")
        _, prefix = self._config(connection)
        name = "/".join((*asset.namespace, asset.name))
        if prefix and not name.startswith(prefix.rstrip("/") + "/"):
            raise ValueError("Azure Blob asset is outside the configured prefix")
        blob_client = self._container_client(connection, secrets).get_blob_client(name)
        properties = blob_client.get_blob_properties()
        expected_size = getattr(properties, "size", None)
        etag = getattr(properties, "etag", None)
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or not etag:
            raise ValueError("Azure Blob properties must include a valid size and ETag")
        if expected_size > self.MAX_BLOB_BYTES:
            raise ValueError("Azure Blob JSON object exceeds configured byte limit")
        downloader = blob_client.download_blob(
            max_concurrency=1,
            etag=etag,
            match_condition=_if_not_modified_match_condition(),
        )
        chunks: list[bytes] = []
        downloaded_size = 0
        for chunk in downloader.chunks():
            downloaded_size += len(chunk)
            if downloaded_size > self.MAX_BLOB_BYTES or downloaded_size > expected_size:
                raise ValueError("Azure Blob JSON object exceeds configured byte limit")
            chunks.append(chunk)
        if downloaded_size != expected_size:
            raise ValueError("Azure Blob changed while reading its bounded snapshot")
        body = b"".join(chunks)
        try:
            payload: object = (
                [json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()]
                if name.lower().endswith(".jsonl")
                else json.loads(body)
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Azure Blob object must contain valid JSON or JSONL") from exc
        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise ValueError("Azure Blob JSON object must resolve to an array of records")
        if len(payload) > limit:
            raise ValueError("Azure Blob JSON object exceeds requested row limit")
        rows = tuple(dict(item) for item in payload)
        fields = tuple(
            FieldSchema(name, "json", True) for name in sorted({key for row in rows for key in row})
        )
        digest = hashlib.sha256(body).hexdigest()
        if checkpoint is not None and checkpoint.value == digest:
            rows = ()
        return ConnectorReadResult(fields, rows, SourceCheckpoint("snapshot", digest))


__all__ = ("AzureBlobJsonConnector",)
