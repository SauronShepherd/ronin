"""Resolve bounded, governed dataset snapshots for ML operations."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Mapping
from typing import Any

from studio_core import AssetRef, WorkspaceId
from studio_storage.ports import ArtifactStore, CatalogStore

MAX_DATASET_BYTES = 64 * 1024 * 1024
MAX_DATASET_ROWS = 100_000
MAX_DATASET_COLUMNS = 1_024
_ARTIFACT_REF = re.compile(r"^artifact://sha256/([0-9a-f]{64})$")
_SUPPORTED_MEDIA_TYPES = {"text/csv", "application/x-ndjson"}


class DatasetReferenceError(ValueError):
    """Raised when a governed dataset snapshot cannot be safely resolved."""


class DatasetResolver:
    """Read CSV or JSONL bytes pinned by a workspace-scoped catalog revision."""

    def __init__(self, catalog: CatalogStore, artifacts: ArtifactStore) -> None:
        self._catalog = catalog
        self._artifacts = artifacts

    def resolve(self, workspace_id: WorkspaceId, ref: AssetRef) -> list[dict[str, object]]:
        asset = self._catalog.get_asset(workspace_id, ref.asset_id)
        if asset is None or asset.kind != "dataset":
            raise DatasetReferenceError("ML dataset asset is missing or is not a dataset")
        revision = self._catalog.get_revision(workspace_id, ref)
        if revision is None or revision.ref != ref:
            raise DatasetReferenceError("ML dataset revision is missing")
        metadata = dict(revision.metadata)
        artifact_ref = metadata.get("artifact_ref")
        media_type = metadata.get("media_type")
        match = _ARTIFACT_REF.fullmatch(artifact_ref or "")
        if match is None or media_type not in _SUPPORTED_MEDIA_TYPES:
            raise DatasetReferenceError("ML dataset revision is not backed by a supported artifact")
        digest = match.group(1)
        if revision.content_digest != f"sha256:{digest}":
            raise DatasetReferenceError("ML dataset revision digest does not match its artifact")
        getter = getattr(self._artifacts, "get_bytes_by_storage_ref", None)
        if not callable(getter):
            raise DatasetReferenceError("artifact store cannot resolve dataset storage references")
        try:
            data = getter(artifact_ref, digest=digest)
        except (OSError, TypeError, ValueError, KeyError) as exc:
            raise DatasetReferenceError("ML dataset artifact is unavailable or invalid") from exc
        if not isinstance(data, bytes) or len(data) > MAX_DATASET_BYTES:
            raise DatasetReferenceError("ML dataset artifact exceeds the 64 MiB limit")
        if hashlib.sha256(data).hexdigest() != digest:
            raise DatasetReferenceError("ML dataset artifact content digest is invalid")
        if media_type == "text/csv":
            return self._csv_rows(data)
        return self._jsonl_rows(data)

    @staticmethod
    def _csv_rows(data: bytes) -> list[dict[str, object]]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetReferenceError("ML CSV dataset must be UTF-8") from exc
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if (
            not headers
            or len(headers) > MAX_DATASET_COLUMNS
            or any(not field or field != field.strip() for field in headers)
            or len(headers) != len(set(headers))
        ):
            raise DatasetReferenceError("ML CSV dataset headers must be unique and non-empty")
        rows: list[dict[str, object]] = []
        try:
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise DatasetReferenceError("ML CSV dataset rows must match the header width")
                rows.append(dict(row))
                if len(rows) > MAX_DATASET_ROWS:
                    raise DatasetReferenceError("ML dataset exceeds the 100000 row limit")
        except csv.Error as exc:
            raise DatasetReferenceError("ML CSV dataset is malformed") from exc
        if not rows:
            raise DatasetReferenceError("ML dataset must contain at least one row")
        return rows

    @staticmethod
    def _jsonl_rows(data: bytes) -> list[dict[str, object]]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetReferenceError("ML JSONL dataset must be UTF-8") from exc
        rows: list[dict[str, object]] = []
        columns: set[str] = set()
        try:
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                row: Any = json.loads(line, parse_constant=_reject_json_constant)
                if not isinstance(row, dict) or not all(
                    isinstance(key, str) and key and key == key.strip() for key in row
                ):
                    raise DatasetReferenceError(
                        f"ML JSONL dataset line {line_number} must be an object"
                    )
                columns.update(row)
                if len(columns) > MAX_DATASET_COLUMNS:
                    raise DatasetReferenceError("ML dataset exceeds the 1024 column limit")
                rows.append(row)
                if len(rows) > MAX_DATASET_ROWS:
                    raise DatasetReferenceError("ML dataset exceeds the 100000 row limit")
        except json.JSONDecodeError as exc:
            raise DatasetReferenceError("ML JSONL dataset contains invalid JSON") from exc
        if not rows:
            raise DatasetReferenceError("ML dataset must contain at least one row")
        return rows


def _reject_json_constant(value: str) -> None:
    raise json.JSONDecodeError("non-standard JSON constant is not allowed", value, 0)


def resolve_lab_rows(
    workspace_id: WorkspaceId,
    lab: Any,
    supplied_rows: object,
    resolver: DatasetResolver | None,
) -> list[dict[str, object]]:
    """Use explicitly supplied rows or resolve the Lab's pinned dataset revision."""
    if supplied_rows is not None:
        if not isinstance(supplied_rows, list) or not all(
            isinstance(row, Mapping) for row in supplied_rows
        ):
            raise ValueError("ML rows must be an array of objects")
        return [dict(row) for row in supplied_rows]
    if resolver is None:
        raise DatasetReferenceError("ML dataset catalog and artifact stores are unavailable")
    return resolver.resolve(workspace_id, lab.dataset)


__all__ = (
    "DatasetReferenceError",
    "DatasetResolver",
    "MAX_DATASET_BYTES",
    "MAX_DATASET_COLUMNS",
    "MAX_DATASET_ROWS",
    "resolve_lab_rows",
)
