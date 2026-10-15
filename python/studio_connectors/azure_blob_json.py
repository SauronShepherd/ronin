"""Bounded Azure Blob Storage JSON/JSONL source connector."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
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
        from azure.storage.blob import BlobServiceClient  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Azure Blob JSON connector requires azure-storage-blob") from exc
    return BlobServiceClient


class AzureBlobJsonConnector:
    """Discover and read JSON or JSONL blobs from an Azure container."""

    descriptor = ConnectorDescriptor(
        "azure.blob.json", 1, ConnectorCapabilities(discover=True, read=True)
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
        credential_ref = dict(connection.secret_refs).get("credential")
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or credential_ref is None
        ):
            raise ValueError(
                "Azure Blob requires a clean HTTPS account_url and credential secret-ref"
            )
        credential = secrets.resolve(credential_ref).reveal_text()
        return _azure()(account_url=account_url, credential=credential).get_container_client(
            self._config(connection)[0]
        )

    def discover(
        self, connection: ConnectionDefinition, secrets: SecretResolver
    ) -> tuple[DiscoveredAsset, ...]:
        _, prefix = self._config(connection)
        assets = []
        for blob in self._container_client(connection, secrets).list_blobs(name_starts_with=prefix):
            name = str(blob.name)
            if name.lower().endswith((".json", ".jsonl")):
                parts = tuple(part for part in name.split("/") if part)
                assets.append(
                    DiscoveredAsset(AssetHandle(connection.id, parts[:-1], parts[-1]), "blob", ())
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
        if page_size < 1 or page_size > 10_000:
            raise ValueError("Azure discovery page_size must be between 1 and 10000")
        _, prefix = self._config(connection)
        listing = self._container_client(connection, secrets).list_blobs(name_starts_with=prefix)
        if not hasattr(listing, "by_page"):
            raise RuntimeError("Azure Blob listing does not expose paginated iteration")
        pages = listing.by_page(continuation_token=cursor, results_per_page=page_size)
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
        body = (
            self._container_client(connection, secrets)
            .get_blob_client(name)
            .download_blob(max_concurrency=1)
            .readall()
        )
        if len(body) > 10 * 1024 * 1024:
            raise ValueError("Azure Blob JSON object exceeds configured byte limit")
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
