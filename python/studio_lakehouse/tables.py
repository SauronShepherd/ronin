"""Provider-neutral open-table contracts shared by Iceberg and Delta adapters."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias, cast, runtime_checkable

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

TableFormat: TypeAlias = Literal["iceberg", "delta"]
TableWriteMode: TypeAlias = Literal["create", "append", "overwrite"]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _identifier(value: str, name: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{name} must start with a letter/underscore and contain only "
            "letters, digits, '_' or '-'"
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


@dataclass(frozen=True, slots=True)
class TableMetadata:
    """Portable table registration keeping logical identity separate from location."""

    identifier: OpenTableIdentifier
    format: TableFormat
    location: str
    managed: bool
    schema: tuple[OpenTableField, ...]
    partition_spec: tuple[str, ...] = ()
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.location or self.location != self.location.strip():
            raise ValueError("table metadata location must be non-empty and trimmed")
        if self.format not in {"iceberg", "delta"}:
            raise ValueError("unsupported table metadata format")
        if not isinstance(self.managed, bool):
            raise TypeError("table metadata managed must be boolean")
        fields = tuple(self.schema)
        if len({field.name for field in fields}) != len(fields):
            raise ValueError("table metadata schema fields must be unique")
        if len(set(self.partition_spec)) != len(self.partition_spec):
            raise ValueError("table metadata partition fields must be unique")
        field_names = {field.name for field in fields}
        if any(field not in field_names for field in self.partition_spec):
            raise ValueError("table metadata partition field must exist in schema")
        properties = tuple(sorted(self.properties))
        if len({key for key, _ in properties}) != len(properties):
            raise ValueError("table metadata properties must be unique")
        if any(
            not isinstance(key, str)
            or not key
            or key != key.strip()
            or not isinstance(value, str)
            or not value
            or value != value.strip()
            for key, value in properties
        ):
            raise ValueError("table metadata properties must be non-empty trimmed strings")
        object.__setattr__(self, "schema", fields)
        object.__setattr__(self, "partition_spec", tuple(self.partition_spec))
        object.__setattr__(self, "properties", properties)

    def to_data(self) -> dict[str, object]:
        return {
            "identifier": self.identifier.qualified_name,
            "format": self.format,
            "location": self.location,
            "managed": self.managed,
            "schema": [
                {"name": field.name, "data_type": field.data_type, "nullable": field.nullable}
                for field in self.schema
            ],
            "partition_spec": list(self.partition_spec),
            "properties": dict(self.properties),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_data()).decode()

    @classmethod
    def from_data(cls, value: object) -> TableMetadata:
        if not isinstance(value, Mapping):
            raise TypeError("table metadata must be an object")
        expected = {
            "identifier",
            "format",
            "location",
            "managed",
            "schema",
            "partition_spec",
            "properties",
        }
        if set(value) != expected:
            raise ValueError("table metadata has invalid shape")
        identifier_text = value["identifier"]
        if not isinstance(identifier_text, str) or identifier_text.count(".") < 1:
            raise ValueError("table metadata identifier must be qualified")
        namespace = tuple(identifier_text.split("."))
        fields = value["schema"]
        if not isinstance(fields, list):
            raise TypeError("table metadata schema must be an array")
        parsed_fields: list[OpenTableField] = []
        for field in fields:
            if not isinstance(field, Mapping) or set(field) != {"name", "data_type", "nullable"}:
                raise ValueError("table metadata field has invalid shape")
            if not isinstance(field["name"], str) or not isinstance(field["data_type"], str):
                raise TypeError("table metadata field names/types must be strings")
            if not isinstance(field["nullable"], bool):
                raise TypeError("table metadata field nullable must be boolean")
            parsed_fields.append(
                OpenTableField(field["name"], field["data_type"], field["nullable"])
            )
        partitions = value["partition_spec"]
        properties = value["properties"]
        if not isinstance(partitions, list) or not all(
            isinstance(item, str) for item in partitions
        ):
            raise TypeError("table metadata partition_spec must be an array of strings")
        if not isinstance(properties, Mapping) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in properties.items()
        ):
            raise TypeError("table metadata properties must be a string object")
        if not isinstance(value["format"], str) or not isinstance(value["location"], str):
            raise TypeError("table metadata format/location must be strings")
        if not isinstance(value["managed"], bool):
            raise TypeError("table metadata managed must be boolean")
        return cls(
            OpenTableIdentifier(namespace[:-1], namespace[-1]),
            cast(TableFormat, value["format"]),
            value["location"],
            value["managed"],
            tuple(parsed_fields),
            tuple(partitions),
            tuple(sorted(properties.items())),
        )

    @classmethod
    def from_json(cls, payload: str) -> TableMetadata:
        return cls.from_data(decode_canonical_json(payload))

    @property
    def identity(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_data())).hexdigest()


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

    def delete_table(self, identifier: OpenTableIdentifier) -> None: ...


__all__ = (
    "OpenTableField",
    "OpenTableIdentifier",
    "OpenTableState",
    "TableMetadata",
    "OpenTableStore",
    "TableFormat",
    "TableWriteMode",
)
