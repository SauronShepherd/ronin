"""Delta Lake open-table adapter using the optional delta-rs Python binding."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .tables import OpenTableField, OpenTableIdentifier, OpenTableState, TableWriteMode


class DeltaDependencyError(RuntimeError):
    """Raised when the optional Delta dependency is unavailable."""


def _deltalake() -> Any:
    try:
        import deltalake
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DeltaDependencyError(
            "Delta support requires the optional Ronin open-table dependencies"
        ) from exc
    return deltalake


def _pyarrow() -> Any:
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise DeltaDependencyError(
            "Delta support requires PyArrow from the optional data-plane dependencies"
        ) from exc
    return pa


def _rows_table(rows: tuple[Mapping[str, object], ...]) -> Any:
    if not rows:
        raise ValueError("Delta writes require at least one row")
    names = tuple(sorted(rows[0]))
    expected = set(names)
    if not names:
        raise ValueError("Delta rows must contain at least one column")
    for row in rows:
        if set(row) != expected:
            raise ValueError("Delta rows must have a consistent object shape")
    pa = _pyarrow()
    return pa.Table.from_pylist([dict(row) for row in rows])


def _field_state(schema: Any) -> tuple[OpenTableField, ...]:
    return tuple(
        OpenTableField(field.name, str(field.type), field.nullable)
        for field in schema
    )


class DeltaTableStore:
    """Local/object-store Delta lifecycle over an explicit table root."""

    format = "delta"

    def __init__(self, warehouse: Path | str) -> None:
        root = Path(warehouse).expanduser()
        self._warehouse = root.resolve()
        self._warehouse.mkdir(parents=True, exist_ok=True)

    def _path(self, identifier: OpenTableIdentifier) -> Path:
        path = self._warehouse.joinpath(*identifier.namespace, identifier.name).resolve()
        try:
            path.relative_to(self._warehouse)
        except ValueError as exc:
            raise ValueError("Delta table path escapes configured warehouse") from exc
        return path

    def write_rows(
        self,
        identifier: OpenTableIdentifier,
        rows: tuple[Mapping[str, object], ...],
        *,
        mode: TableWriteMode = "create",
    ) -> OpenTableState:
        if mode not in {"create", "append", "overwrite"}:
            raise ValueError("unsupported Delta write mode")
        deltalake = _deltalake()
        table = _rows_table(rows)
        path = self._path(identifier)
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.joinpath("_delta_log").exists()
        if mode == "create" and exists:
            raise FileExistsError(f"Delta table already exists: {identifier.qualified_name}")
        if mode == "append" and not exists:
            raise FileNotFoundError(f"Delta table does not exist: {identifier.qualified_name}")
        write_mode = "error" if mode == "create" else mode
        deltalake.write_deltalake(str(path), table, mode=write_mode)
        return self.inspect(identifier)

    def read_rows(
        self,
        identifier: OpenTableIdentifier,
        *,
        columns: tuple[str, ...] | None = None,
        limit: int = 10_000,
        version: str | None = None,
    ) -> tuple[dict[str, object], ...]:
        if limit < 1 or limit > 100_000:
            raise ValueError("Delta read limit must be between 1 and 100000")
        deltalake = _deltalake()
        path = self._path(identifier)
        kwargs: dict[str, object] = {}
        if version is not None:
            try:
                kwargs["version"] = int(version)
            except ValueError as exc:
                raise ValueError("Delta version must be an integer string") from exc
        table = deltalake.DeltaTable(str(path), **kwargs)
        arrow = table.to_pyarrow_table(columns=list(columns) if columns is not None else None)
        if arrow.num_rows > limit:
            raise ValueError("Delta result exceeds requested row limit")
        return tuple(dict(row) for row in arrow.to_pylist())

    def inspect(self, identifier: OpenTableIdentifier) -> OpenTableState:
        deltalake = _deltalake()
        path = self._path(identifier)
        table = deltalake.DeltaTable(str(path))
        arrow = table.to_pyarrow_table().schema
        metadata = table.metadata()
        configuration = metadata.configuration or {}
        return OpenTableState(
            "delta",
            identifier,
            str(path),
            str(table.version()),
            _field_state(arrow),
            tuple(sorted((str(key), str(value)) for key, value in configuration.items())),
        )


__all__ = ("DeltaDependencyError", "DeltaTableStore")
