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

from .contracts import ConnectorCommitResult, ConnectorReadResult, DiscoveryPage


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
    """Read S3 JSON/JSONL objects and publish bounded at-least-once sink writes."""

    MAX_OBJECT_BYTES = 10 * 1024 * 1024
    MAX_BATCH_SIZE = 10_000

    descriptor = ConnectorDescriptor(
        "s3.json",
        1,
        ConnectorCapabilities(
            discover=True,
            read=True,
            write=True,
            max_page_size=10_000,
            max_batch_size=MAX_BATCH_SIZE,
        ),
    )

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
        body = response["Body"].read(self.MAX_OBJECT_BYTES + 1)
        if len(body) > self.MAX_OBJECT_BYTES:
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

    def write(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        result: ConnectorReadResult,
        secrets: SecretResolver,
        *,
        idempotency_key: str,
    ) -> ConnectorCommitResult:
        """Replace one JSON/JSONL object; retries are at-least-once, never transactional.

        A stable caller key is echoed in the commit receipt and a hash is stored as
        object metadata for diagnostics. S3-compatible PUT does not enforce that key,
        so this adapter makes no exactly-once or provider-idempotency claim.
        """

        del secrets
        if asset.connection_id != connection.id:
            raise ValueError("S3 asset handle does not belong to the connection")
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key
            or idempotency_key != idempotency_key.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in idempotency_key)
        ):
            raise ValueError("idempotency_key must be non-empty trimmed text")
        try:
            idempotency_key_bytes = idempotency_key.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("idempotency_key must contain valid UTF-8 text") from exc
        if len(idempotency_key_bytes) > 1024:
            raise ValueError("idempotency_key must be at most 1024 bytes")
        if len(result.rows) > self.MAX_BATCH_SIZE:
            raise ValueError("S3 JSON write exceeds configured row limit")

        bucket, prefix = self._config(connection)
        parts = (*asset.namespace, asset.name)
        if any(
            not part
            or part in {".", ".."}
            or "/" in part
            or "\\" in part
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in part)
            for part in parts
        ):
            raise ValueError("S3 asset path contains an unsafe component")
        key = "/".join(parts)
        if prefix and not key.startswith(prefix.rstrip("/") + "/"):
            raise ValueError("S3 asset is outside the configured prefix")
        try:
            key_bytes = key.encode("utf-8")
            output_id = f"s3://{bucket}/{key}"
            output_id_bytes = output_id.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("S3 asset path must contain valid UTF-8 text") from exc
        if len(key_bytes) > 1024:
            raise ValueError("S3 object key exceeds the 1024-byte provider limit")
        if len(output_id_bytes) > 1024:
            raise ValueError("S3 output id exceeds the 1024-byte connector receipt limit")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in output_id):
            raise ValueError("S3 output id must not contain control characters")

        suffix = asset.name.lower()
        if suffix.endswith(".jsonl"):
            media_type = "application/x-ndjson"
            jsonl = True
        elif suffix.endswith(".json"):
            media_type = "application/json"
            jsonl = False
        else:
            raise ValueError("S3 JSON sink only supports .json and .jsonl assets")

        encoder = json.JSONEncoder(
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        chunks: list[bytes] = []
        size_bytes = 0

        def append_text(value: str) -> None:
            nonlocal size_bytes
            encoded = value.encode("utf-8")
            size_bytes += len(encoded)
            if size_bytes > self.MAX_OBJECT_BYTES:
                raise ValueError("S3 JSON write exceeds configured byte limit")
            chunks.append(encoded)

        try:
            if jsonl:
                for row in result.rows:
                    for piece in encoder.iterencode(row):
                        append_text(piece)
                    append_text("\n")
            else:
                append_text("[")
                for index, row in enumerate(result.rows):
                    if index:
                        append_text(",")
                    for piece in encoder.iterencode(row):
                        append_text(piece)
                append_text("]")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith("S3 JSON write exceeds"):
                raise
            raise ValueError("S3 JSON rows must contain valid, finite JSON values") from exc

        payload = b"".join(chunks)
        digest = hashlib.sha256(payload).hexdigest()
        response = self._client_for(connection).put_object(
            Bucket=bucket,
            Key=key,
            Body=payload,
            ContentType=media_type,
            Metadata={
                "ronin-idempotency-key-sha256": hashlib.sha256(idempotency_key_bytes).hexdigest(),
                "ronin-output-sha256": digest,
            },
        )
        commit_id = ""
        if isinstance(response, Mapping):
            version_id = response.get("VersionId")
            etag = response.get("ETag")
            if isinstance(version_id, str) and version_id:
                commit_id = version_id
            elif isinstance(etag, str) and etag:
                commit_id = etag.strip('"')
        try:
            commit_id_bytes = commit_id.encode("utf-8")
        except UnicodeEncodeError:
            commit_id_bytes = b""
        if (
            not commit_id
            or not commit_id_bytes
            or commit_id != commit_id.strip()
            or len(commit_id_bytes) > 1024
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in commit_id)
        ):
            commit_id = f"sha256:{digest}"
        return ConnectorCommitResult(
            idempotency_key=idempotency_key,
            commit_id=commit_id,
            output_id=output_id,
            output_digest=digest,
            transactional=False,
            idempotency_enforced=False,
            delivery_semantics="at_least_once",
        )


__all__ = ("S3JsonConnector",)
