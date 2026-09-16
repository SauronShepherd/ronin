"""Executable connector contracts layered over portable connection definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar, runtime_checkable

from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
)
from studio_storage.secrets import SecretResolver

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DiscoveryPage(Generic[T]):
    """Bounded connector discovery page with an opaque provider cursor."""

    items: tuple[T, ...]
    next_cursor: str | None
    truncated: bool
    source_version: str | None = None

    def __post_init__(self) -> None:
        if self.next_cursor is not None and not self.next_cursor:
            raise ValueError("discovery next_cursor must be non-empty when present")
        if not self.truncated and self.next_cursor is not None:
            raise ValueError("non-truncated discovery page must not have a cursor")


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


@runtime_checkable
class PagedConnector(Protocol):
    """Connector capability for bounded, cursor-based asset discovery."""

    def discover_page(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
        *,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> DiscoveryPage[DiscoveredAsset]: ...


__all__ = ("Connector", "ConnectorReadResult", "DiscoveryPage", "PagedConnector")
