"""Executable connector contracts layered over portable connection definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
)
from studio_storage.secrets import SecretResolver


@dataclass(frozen=True, slots=True)
class ConnectorReadResult:
    fields: tuple[FieldSchema, ...]
    rows: tuple[dict[str, object], ...]
    checkpoint: SourceCheckpoint | None = None

    def __post_init__(self) -> None:
        field_names = tuple(field.name for field in self.fields)
        if len(field_names) != len(set(field_names)):
            raise ValueError("connector result field names must be unique")
        expected = set(field_names)
        for row in self.rows:
            if set(row) != expected:
                raise ValueError("connector result rows must match declared fields exactly")


@runtime_checkable
class Connector(Protocol):
    @property
    def descriptor(self) -> ConnectorDescriptor: ...

    def discover(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
    ) -> tuple[DiscoveredAsset, ...]: ...

    def read(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        secrets: SecretResolver,
        *,
        limit: int = 10_000,
        checkpoint: SourceCheckpoint | None = None,
    ) -> ConnectorReadResult: ...


__all__ = ("Connector", "ConnectorReadResult")
