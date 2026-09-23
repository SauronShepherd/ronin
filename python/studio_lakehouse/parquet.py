"""Optional PyArrow-backed Parquet reference implementation.

The dependency is intentionally optional so Ronin's minimal control-plane install
stays small. Callers get a typed error when the data-plane extra is unavailable.
"""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterable, Mapping
from contextlib import suppress
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
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
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
        ParquetSchemaField(field.name, str(field.type), field.nullable) for field in schema
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
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
        pq.write_table(table, temporary_name, compression=compression)
        Path(temporary_name).replace(destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            with suppress(FileNotFoundError):
                Path(temporary_name).unlink()
    return inspect_parquet(destination)


def read_parquet_rows(
    path: Path,
    *,
    columns: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> tuple[dict[str, object], ...]:
    """Read local Parquet rows with optional projection and result bound."""

    if limit is not None and not 0 <= limit <= 100_000:
        raise ValueError("Parquet read limit must be between 0 and 100000")
    if columns is not None and any(not column or column != column.strip() for column in columns):
        raise ValueError("Parquet projection columns must be non-empty and trimmed")
    if columns is not None and len(set(columns)) != len(columns):
        raise ValueError("Parquet projection columns must be unique")
    _, pq = _pyarrow()
    resolved = path.resolve(strict=True)
    selected_columns = list(columns) if columns else None
    if limit is None:
        table = pq.read_table(resolved, columns=selected_columns)
        return tuple(dict(row) for row in table.to_pylist())
    if limit == 0:
        return ()
    rows: list[dict[str, object]] = []
    parquet_file = pq.ParquetFile(resolved)
    for batch in parquet_file.iter_batches(batch_size=min(limit, 1024), columns=selected_columns):
        rows.extend(dict(row) for row in batch.to_pylist())
        if len(rows) >= limit:
            break
    return tuple(rows[:limit])


__all__ = (
    "ParquetDependencyError",
    "ParquetFile",
    "ParquetSchemaField",
    "inspect_parquet",
    "read_parquet_rows",
    "write_parquet_rows",
)
