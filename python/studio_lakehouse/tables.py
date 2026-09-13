"""Provider-neutral open-table contracts shared by Iceberg and Delta adapters."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias, runtime_checkable

TableFormat: TypeAlias = Literal["iceberg", "delta"]
TableWriteMode: TypeAlias = Literal["create", "append", "overwrite"]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _identifier(value: str, name: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{name} must start with a letter/underscore and contain only letters, digits, '_' or '-'"
        )
    return value


@dataclass(frozen=True, order=True, slots=True)
class OpenTableIdentifier:
    """Portable logical table identifier independent of storage/catalog credentials."""

    namespace: tuple[str, ...]
    name: str

    def __post_init__(self) -> None:
        if not self.namespace:
            raise ValueError("open table identifier requires at least one namespace component")
        object.__setattr__(
            self,
            "namespace",
            tuple(_identifier(item, "table namespace") for item in self.namespace),
        )
        object.__setattr__(self, "name", _identifier(self.name, "table name"))

    @property
    def qualified_name(self) -> str:
        return ".".join((*self.namespace, self.name))


@dataclass(frozen=True, order=True, slots=True)
class OpenTableField:
    name: str
    data_type: str
    nullable: bool

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip():
            raise ValueError("open table field name must be non-empty and trimmed")
        if not self.data_type or self.data_type != self.data_type.strip():
            raise ValueError("open table field data_type must be non-empty and trimmed")


@dataclass(frozen=True, slots=True)
class OpenTableState:
    format: TableFormat
    identifier: OpenTableIdentifier
    location: str
    version: str | None
    fields: tuple[OpenTableField, ...]
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.format not in {"iceberg", "delta"}:
            raise ValueError("unsupported open table format")
        if not self.location or self.location != self.location.strip():
            raise ValueError("open table location must be non-empty and trimmed")
        fields = tuple(self.fields)
        names = [field.name for field in fields]
        if len(names) != len(set(names)):
            raise ValueError("open table field names must be unique")
        properties = tuple(sorted(self.properties))
        keys = [key for key, _ in properties]
        if len(keys) != len(set(keys)):
            raise ValueError("open table property keys must be unique")
        for key, value in properties:
            if not key or key != key.strip() or not value or value != value.strip():
                raise ValueError("open table properties must be non-empty trimmed strings")
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "properties", properties)


@runtime_checkable
class OpenTableStore(Protocol):
    """Minimal executable table lifecycle shared by reference and production adapters."""

    format: TableFormat

    def write_rows(
        self,
        identifier: OpenTableIdentifier,
        rows: tuple[Mapping[str, object], ...],
        *,
        mode: TableWriteMode = "create",
    ) -> OpenTableState: ...

    def read_rows(
        self,
        identifier: OpenTableIdentifier,
        *,
        columns: tuple[str, ...] | None = None,
        limit: int = 10_000,
        version: str | None = None,
    ) -> tuple[dict[str, object], ...]: ...

    def inspect(self, identifier: OpenTableIdentifier) -> OpenTableState: ...


__all__ = (
    "OpenTableField",
    "OpenTableIdentifier",
    "OpenTableState",
    "OpenTableStore",
    "TableFormat",
    "TableWriteMode",
)
