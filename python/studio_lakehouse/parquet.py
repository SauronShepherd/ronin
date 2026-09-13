"""Optional PyArrow-backed Parquet reference implementation.

The dependency is intentionally optional so Ronin's minimal control-plane install
stays small. Callers get a typed error when the data-plane extra is unavailable.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ParquetDependencyError(RuntimeError):
    """Raised when the optional PyArrow dependency is not installed."""


@dataclass(frozen=True, slots=True)
class ParquetSchemaField:
    name: str
    type_name: str
    nullable: bool


@dataclass(frozen=True, slots=True)
class ParquetFile:
    path: Path
    sha256: str
    rows: int
    bytes: int
    schema: tuple[ParquetSchemaField, ...]


def _pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on optional installation
        raise ParquetDependencyError(
            "Parquet support requires the optional Ronin data-plane dependencies"
        ) from exc
    return pa, pq


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_fields(schema: Any) -> tuple[ParquetSchemaField, ...]:
    return tuple(
        ParquetSchemaField(field.name, str(field.type), field.nullable)
        for field in schema
    )


def inspect_parquet(path: Path) -> ParquetFile:
    """Inspect one local Parquet file and return content-addressed metadata."""

    _, pq = _pyarrow()
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Parquet path must reference a regular file")
    metadata = pq.read_metadata(resolved)
    schema = metadata.schema.to_arrow_schema()
    return ParquetFile(
        resolved,
        _digest_file(resolved),
        metadata.num_rows,
        resolved.stat().st_size,
        _schema_fields(schema),
    )


def write_parquet_rows(
    path: Path,
    rows: Iterable[Mapping[str, object]],
    *,
    compression: str = "zstd",
) -> ParquetFile:
    """Write JSON-like rows to one deterministic-location Parquet file.

    Row ordering is preserved. Schema inference is delegated to PyArrow and is
    therefore a reference path, not yet the final governed schema-policy layer.
    """

    pa, pq = _pyarrow()
    materialized = [dict(row) for row in rows]
    if not materialized:
        raise ValueError("cannot infer Parquet schema from an empty row collection")
    keys = tuple(materialized[0])
    if not keys:
        raise ValueError("Parquet rows must contain at least one field")
    key_set = set(keys)
    for row in materialized:
        if set(row) != key_set:
            raise ValueError("all Parquet rows must contain the same fields")

    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(materialized)
    pq.write_table(table, destination, compression=compression)
    return inspect_parquet(destination)


def read_parquet_rows(
    path: Path,
    *,
    columns: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> tuple[dict[str, object], ...]:
    """Read local Parquet rows with optional projection and result bound."""

    if limit is not None and limit < 0:
        raise ValueError("Parquet read limit must be non-negative")
    _, pq = _pyarrow()
    resolved = path.resolve(strict=True)
    table = pq.read_table(resolved, columns=list(columns) if columns else None)
    if limit is not None:
        table = table.slice(0, limit)
    return tuple(dict(row) for row in table.to_pylist())


__all__ = (
    "ParquetDependencyError",
    "ParquetFile",
    "ParquetSchemaField",
    "inspect_parquet",
    "read_parquet_rows",
    "write_parquet_rows",
)
