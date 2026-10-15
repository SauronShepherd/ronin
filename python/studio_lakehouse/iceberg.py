"""Apache Iceberg open-table adapter using the optional PyIceberg runtime."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from .tables import OpenTableField, OpenTableIdentifier, OpenTableState, TableWriteMode


class IcebergDependencyError(RuntimeError):
    """Raised when the optional PyIceberg dependency is unavailable."""


class IcebergCapabilityError(RuntimeError):
    """Raised when the configured Iceberg runtime lacks a requested capability."""


@dataclass(frozen=True, slots=True)
class IcebergCompatibilityProfile:
    """Declared reference boundary for the optional PyIceberg adapter."""

    spec_version: str = "1.4"
    capabilities: tuple[str, ...] = (
        "create",
        "append",
        "overwrite",
        "delete",
        "snapshot-read",
        "partition-spec",
    )
    unsupported_features: tuple[str, ...] = (
        "schema-evolution",
        "metadata-cleanup-policy",
        "catalog-agnostic-certification",
    )


def _pyiceberg_catalog() -> Any:
    try:
        return import_module("pyiceberg.catalog").load_catalog
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise IcebergDependencyError(
            "Iceberg support requires the optional Ronin open-table dependencies"
        ) from exc


def _pyarrow() -> Any:
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise IcebergDependencyError(
            "Iceberg support requires PyArrow from the optional data-plane dependencies"
        ) from exc
    return pa


def _rows_table(rows: tuple[Mapping[str, object], ...]) -> Any:
    if not rows:
        raise ValueError("Iceberg writes require at least one row")
    names = tuple(sorted(rows[0]))
    expected = set(names)
    if not names:
        raise ValueError("Iceberg rows must contain at least one column")
    for row in rows:
        if set(row) != expected:
            raise ValueError("Iceberg rows must have a consistent object shape")
    return _pyarrow().Table.from_pylist([dict(row) for row in rows])


def _field_state(schema: Any) -> tuple[OpenTableField, ...]:
    return tuple(OpenTableField(field.name, str(field.type), field.nullable) for field in schema)


class IcebergTableStore:
    """Iceberg lifecycle through one explicitly configured PyIceberg catalog."""

    format = "iceberg"
    compatibility = IcebergCompatibilityProfile()

    def __init__(
        self,
        *,
        catalog_name: str = "ronin",
        catalog_properties: Mapping[str, str] | None = None,
    ) -> None:
        if not catalog_name or catalog_name != catalog_name.strip():
            raise ValueError("Iceberg catalog_name must be non-empty and trimmed")
        load_catalog = _pyiceberg_catalog()
        self._catalog = load_catalog(catalog_name, **dict(catalog_properties or {}))

    @staticmethod
    def _identifier(identifier: OpenTableIdentifier) -> tuple[str, ...]:
        return (*identifier.namespace, identifier.name)

    def _load(self, identifier: OpenTableIdentifier) -> Any:
        try:
            return self._catalog.load_table(self._identifier(identifier))
        except Exception as exc:
            raise FileNotFoundError(
                f"Iceberg table does not exist: {identifier.qualified_name}"
            ) from exc

    def write_rows(
        self,
        identifier: OpenTableIdentifier,
        rows: tuple[Mapping[str, object], ...],
        *,
        mode: TableWriteMode = "create",
    ) -> OpenTableState:
        if mode not in {"create", "append", "overwrite"}:
            raise ValueError("unsupported Iceberg write mode")
        arrow = _rows_table(rows)
        table_identifier = self._identifier(identifier)
        if mode == "create":
            try:
                self._catalog.load_table(table_identifier)
            except Exception:
                for index in range(1, len(identifier.namespace) + 1):
                    namespace = identifier.namespace[:index]
                    with suppress(Exception):
                        self._catalog.create_namespace(namespace)
                self._catalog.create_table(table_identifier, schema=arrow.schema)
            else:
                raise FileExistsError(f"Iceberg table already exists: {identifier.qualified_name}")
            table = self._catalog.load_table(table_identifier)
            table.append(arrow)
        elif mode == "append":
            table = self._load(identifier)
            table.append(arrow)
        else:
            table = self._load(identifier)
            if hasattr(table, "overwrite"):
                table.overwrite(arrow)
            else:
                raise IcebergCapabilityError(
                    "configured PyIceberg runtime does not expose overwrite support"
                )
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
            raise ValueError("Iceberg read limit must be between 1 and 100000")
        if columns is not None:
            if any(not column or column != column.strip() for column in columns):
                raise ValueError("Iceberg projection columns must be non-empty and trimmed")
            if len(set(columns)) != len(columns):
                raise ValueError("Iceberg projection columns must be unique")
        table = self._load(identifier)
        if version is not None:
            try:
                snapshot_id = int(version)
            except ValueError as exc:
                raise ValueError("Iceberg version must be a snapshot id integer string") from exc
            if snapshot_id < 0:
                raise ValueError("Iceberg version must be non-negative")
            scan = table.scan(
                selected_fields=columns or ("*",),
                snapshot_id=snapshot_id,
                limit=limit + 1,
            )
        else:
            scan = table.scan(
                selected_fields=columns or ("*",),
                limit=limit + 1,
            )
        arrow = scan.to_arrow()
        if arrow.num_rows > limit:
            raise ValueError("Iceberg result exceeds requested row limit")
        return tuple(dict(row) for row in arrow.to_pylist())

    def inspect(self, identifier: OpenTableIdentifier) -> OpenTableState:
        table = self._load(identifier)
        schema = table.scan(limit=0).to_arrow().schema
        snapshot = table.current_snapshot()
        version = None if snapshot is None else str(snapshot.snapshot_id)
        properties = getattr(table.metadata, "properties", {}) or {}
        location = getattr(table.metadata, "location", identifier.qualified_name)
        return OpenTableState(
            "iceberg",
            identifier,
            str(location),
            version,
            _field_state(schema),
            tuple(sorted((str(key), str(value)) for key, value in properties.items())),
        )

    def delete_table(self, identifier: OpenTableIdentifier) -> None:
        """Drop a table from the configured catalog, including data when supported."""
        drop_table = getattr(self._catalog, "drop_table", None)
        if not callable(drop_table):
            raise IcebergCapabilityError(
                "configured PyIceberg catalog does not expose table deletion"
            )
        try:
            drop_table(self._identifier(identifier), purge=True)
        except TypeError:
            drop_table(self._identifier(identifier))
        except Exception as exc:
            raise FileNotFoundError(
                f"Iceberg table does not exist: {identifier.qualified_name}"
            ) from exc


__all__ = ("IcebergCapabilityError", "IcebergDependencyError", "IcebergTableStore")
