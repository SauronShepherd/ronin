"""Bounded S3-compatible JSON/JSONL source connector."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

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


def _boto3() -> Any:
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("S3 JSON connector requires the optional boto3 dependency") from exc
    return boto3


def _fields(rows: tuple[dict[str, object], ...]) -> tuple[FieldSchema, ...]:
    names = sorted({key for row in rows for key in row})
    return tuple(FieldSchema(name, "json", True) for name in names)


class S3JsonConnector:
    """Discover and read JSON or JSONL objects from an S3-compatible bucket."""

    descriptor = ConnectorDescriptor("s3.json", 1, ConnectorCapabilities(discover=True, read=True))

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def _config(self, connection: ConnectionDefinition) -> tuple[str, str]:
        if connection.connector_id != self.descriptor.connector_id:
            raise ValueError("connection does not target the S3 JSON connector")
        options = dict(connection.options)
        bucket = options.get("bucket", "").strip()
        prefix = options.get("prefix", "").strip()
        if not bucket or bucket.startswith(".") or "/" in bucket:
            raise ValueError("S3 bucket must be a non-empty bucket name")
        if ".." in prefix.split("/"):
            raise ValueError("S3 prefix contains unsafe path components")
        addressing_style = options.get("addressing_style", "auto")
        if addressing_style not in {"auto", "path", "virtual"}:
            raise ValueError("S3 addressing_style must be auto, path, or virtual")
        return bucket, prefix

    def _client_for(self, connection: ConnectionDefinition) -> Any:
        if self._client is not None:
            return self._client
        options = dict(connection.options)
        kwargs = {key: options[key] for key in ("endpoint_url", "region_name") if options.get(key)}
        try:
            config_module = __import__("botocore.config", fromlist=["Config"])
            kwargs["config"] = config_module.Config(
                retries={"mode": "standard", "max_attempts": 3},
                s3={"addressing_style": options.get("addressing_style", "auto")},
            )
        except ImportError:  # pragma: no cover - boto3 normally brings botocore
            pass
        return _boto3().client("s3", **kwargs)

    def discover(
        self, connection: ConnectionDefinition, secrets: SecretResolver
    ) -> tuple[DiscoveredAsset, ...]:
        del secrets
        bucket, prefix = self._config(connection)
        client = self._client_for(connection)
        assets: list[DiscoveredAsset] = []
        token: str | None = None
        while True:
            request = {"Bucket": bucket, "Prefix": prefix}
            if token:
                request["ContinuationToken"] = token
            page = client.list_objects_v2(**request)
            for item in page.get("Contents", ()):
                key = str(item.get("Key", ""))
                if key and not key.endswith("/") and key.lower().endswith((".json", ".jsonl")):
                    parts = tuple(part for part in key.split("/") if part)
                    assets.append(
                        DiscoveredAsset(
                            AssetHandle(connection.id, parts[:-1], parts[-1]), "object", ()
                        )
                    )
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
            if not token:
                raise ValueError("S3 listing was truncated without a continuation token")
        return tuple(sorted(assets, key=lambda item: item.handle.qualified_name))

    def discover_page(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
        *,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> DiscoveryPage[DiscoveredAsset]:
        """Discover one bounded S3 page; ``cursor`` is opaque to callers."""
        del secrets
        if page_size < 1 or page_size > 10_000:
            raise ValueError("S3 discovery page_size must be between 1 and 10000")
        bucket, prefix = self._config(connection)
        request: dict[str, object] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": page_size}
        if cursor is not None:
            request["ContinuationToken"] = cursor
        page = self._client_for(connection).list_objects_v2(**request)
        assets = tuple(
            DiscoveredAsset(
                AssetHandle(
                    connection.id,
                    tuple(part for part in str(item["Key"]).split("/") if part)[:-1],
                    str(item["Key"]).split("/")[-1],
                ),
                "object",
                (),
            )
            for item in page.get("Contents", ())
            if str(item.get("Key", "")).lower().endswith((".json", ".jsonl"))
            and not str(item.get("Key", "")).endswith("/")
        )
        truncated = bool(page.get("IsTruncated"))
        next_cursor = page.get("NextContinuationToken")
        if truncated and not isinstance(next_cursor, str):
            raise ValueError("S3 listing was truncated without a continuation token")
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
        del secrets
        if checkpoint is not None and checkpoint.strategy != "snapshot":
            raise ValueError("S3 JSON connector only supports snapshot checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("S3 read limit must be between 1 and 100000")
        if asset.connection_id != connection.id or not asset.name:
            raise ValueError("S3 asset handle does not belong to the connection")
        bucket, prefix = self._config(connection)
        key = "/".join((*asset.namespace, asset.name))
        if prefix and not key.startswith(prefix.rstrip("/") + "/"):
            raise ValueError("S3 asset is outside the configured prefix")
        response = self._client_for(connection).get_object(Bucket=bucket, Key=key)
        body = response["Body"].read(10 * 1024 * 1024 + 1)
        if len(body) > 10 * 1024 * 1024:
            raise ValueError("S3 JSON object exceeds configured byte limit")
        try:
            if key.lower().endswith(".jsonl"):
                payload: object = [
                    json.loads(line) for line in body.decode("utf-8").splitlines() if line.strip()
                ]
            else:
                payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("S3 object must contain valid JSON or JSONL") from exc
        if not isinstance(payload, list) or not all(isinstance(item, Mapping) for item in payload):
            raise ValueError("S3 JSON object must resolve to an array of records")
        if len(payload) > limit:
            raise ValueError("S3 JSON object exceeds requested row limit")
        rows = tuple(dict(item) for item in payload)
        checkpoint_value = hashlib.sha256(body).hexdigest()
        if checkpoint is not None and checkpoint.value == checkpoint_value:
            rows = ()
        return ConnectorReadResult(
            _fields(rows if rows else tuple(dict(item) for item in payload)),
            rows,
            SourceCheckpoint("snapshot", checkpoint_value),
        )


__all__ = ("S3JsonConnector",)
