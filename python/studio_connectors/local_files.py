"""Safe local CSV/JSONL reference connector and governed ingestion path."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    ConnectionDefinition,
    DiscoveredAsset,
    FieldSchema,
    LineageEdge,
    SourceCheckpoint,
    WorkspaceId,
)
from studio_core.connections import AssetHandle
from studio_orchestrator import Instant
from studio_storage import LocalArtifactStore, SqliteCatalogStore

_LOCAL_FILE_CONNECTOR_ID = "ronin.local-file"
_SUPPORTED_SUFFIXES = {".csv", ".jsonl"}
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LocalFileIngestionResult:
    source: AssetRef
    target: AssetRef
    checkpoint: SourceCheckpoint
    artifact_ref: str
    discovered: DiscoveredAsset


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    if not relative_path or relative_path != relative_path.strip():
        raise ValueError("relative path must be non-empty and trimmed")
    candidate = root.joinpath(relative_path)
    root_resolved = root.resolve(strict=True)
    candidate_resolved = candidate.resolve(strict=True)
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("source path escapes connector root") from exc
    current = candidate
    while current != root:
        if current.is_symlink():
            raise ValueError("source path must not traverse symlinks")
        current = current.parent
    if not candidate_resolved.is_file():
        raise ValueError("source path must reference a regular file")
    if candidate_resolved.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise ValueError("local file connector supports only CSV and JSONL")
    return candidate_resolved


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise ValueError("unsupported JSON value type")


def _discover_csv(connection: ConnectionDefinition, name: str, data: bytes) -> DiscoveredAsset:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV input must be UTF-8") from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV input must contain a header row") from exc
    if not header or any(not column or column != column.strip() for column in header):
        raise ValueError("CSV header fields must be non-empty and trimmed")
    if len(header) != len(set(header)):
        raise ValueError("CSV header fields must be unique")
    fields = tuple(FieldSchema(column, "string", True) for column in header)
    handle = AssetHandle(connection.id, (), name)
    return DiscoveredAsset(handle=handle, kind="file", fields=fields)


def _discover_jsonl(
    connection: ConnectionDefinition, name: str, data: bytes
) -> DiscoveredAsset:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("JSONL input must be UTF-8") from exc
    observed: dict[str, set[str]] = {}
    record_count = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL record at line {line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError("JSONL records must be JSON objects")
        record_count += 1
        for key, item in value.items():
            if not isinstance(key, str) or not key or key != key.strip():
                raise ValueError("JSONL object keys must be non-empty and trimmed")
            observed.setdefault(key, set()).add(_json_type(item))
    if record_count == 0:
        raise ValueError("JSONL input must contain at least one object record")
    fields = tuple(
        FieldSchema(
            name=key,
            data_type=next(iter(types)) if len(types) == 1 else "mixed",
            nullable="null" in types,
        )
        for key, types in sorted(observed.items())
    )
    handle = AssetHandle(connection.id, (), name)
    return DiscoveredAsset(handle=handle, kind="file", fields=fields)


class LocalFileConnector:
    """Reference local connector with bounded reads and fail-closed path containment."""

    def __init__(self, root: Path, *, max_bytes: int = _DEFAULT_MAX_BYTES) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self._root = root
        self._max_bytes = max_bytes

    @property
    def connector_id(self) -> str:
        return _LOCAL_FILE_CONNECTOR_ID

    def read(self, relative_path: str) -> tuple[Path, bytes, str]:
        path = _safe_relative_path(self._root, relative_path)
        size = path.stat().st_size
        if size > self._max_bytes:
            raise ValueError("source file exceeds connector read limit")
        data = path.read_bytes()
        if len(data) != size:
            raise OSError("source file changed during bounded read")
        media_type = "text/csv" if path.suffix.lower() == ".csv" else "application/x-ndjson"
        return path, data, media_type

    def discover(self, connection: ConnectionDefinition, relative_path: str) -> DiscoveredAsset:
        if connection.connector_id != self.connector_id:
            raise ValueError("connection does not target the local file connector")
        path, data, _media_type = self.read(relative_path)
        if path.suffix.lower() == ".csv":
            return _discover_csv(connection, relative_path, data)
        return _discover_jsonl(connection, relative_path, data)

    def ingest(
        self,
        *,
        workspace_id: WorkspaceId,
        connection: ConnectionDefinition,
        relative_path: str,
        target_asset_id: AssetId,
        target_name: str,
        artifact_store: LocalArtifactStore,
        catalog_store: SqliteCatalogStore,
        now: Instant | str,
    ) -> LocalFileIngestionResult:
        if connection.connector_id != self.connector_id:
            raise ValueError("connection does not target the local file connector")
        path, data, media_type = self.read(relative_path)
        discovered = (
            _discover_csv(connection, relative_path, data)
            if path.suffix.lower() == ".csv"
            else _discover_jsonl(connection, relative_path, data)
        )
        digest = hashlib.sha256(data).hexdigest()
        version = AssetVersion(f"sha256:{digest}")
        source_id = AssetId(
            "source-" + hashlib.sha256(
                f"{connection.id.value}\n{relative_path}".encode("utf-8")
            ).hexdigest()[:32]
        )
        source_ref = AssetRef(source_id, version)
        target_ref = AssetRef(target_asset_id, version)
        artifact = artifact_store.put_bytes(
            role="ingestion-source",
            data=data,
            media_type=media_type,
        )
        source_asset = CatalogAsset(
            id=source_id,
            kind="file",
            name=relative_path,
            properties=(("connection_id", connection.id.value),),
        )
        target_asset = CatalogAsset(
            id=target_asset_id,
            kind="dataset",
            name=target_name,
        )
        catalog_store.create_asset(workspace_id, source_asset, now=now)
        catalog_store.create_asset(workspace_id, target_asset, now=now)
        revision_metadata = (
            ("artifact_ref", artifact.storage_ref),
            ("media_type", media_type),
        )
        source_revision = AssetRevision(
            source_ref,
            content_digest=f"sha256:{digest}",
            metadata=revision_metadata,
        )
        target_revision = AssetRevision(
            target_ref,
            content_digest=f"sha256:{digest}",
            metadata=revision_metadata,
        )
        catalog_store.put_revision(workspace_id, source_revision, now=now)
        catalog_store.put_revision(workspace_id, target_revision, now=now)
        catalog_store.put_lineage(
            workspace_id,
            LineageEdge(
                source=source_ref,
                target=target_ref,
                operation="write",
                mode="observed",
            ),
            now=now,
        )
        return LocalFileIngestionResult(
            source=source_ref,
            target=target_ref,
            checkpoint=SourceCheckpoint("snapshot", digest),
            artifact_ref=artifact.storage_ref,
            discovered=discovered,
        )
