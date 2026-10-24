"""Executable connector contracts layered over portable connection definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar, runtime_checkable

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
        if not isinstance(self.truncated, bool):
            raise ValueError("discovery truncated must be boolean")
        if self.next_cursor is not None and (
            not isinstance(self.next_cursor, str) or not self.next_cursor
        ):
            raise ValueError("discovery next_cursor must be non-empty when present")
        if not self.truncated and self.next_cursor is not None:
            raise ValueError("non-truncated discovery page must not have a cursor")
        if self.truncated and self.next_cursor is None:
            raise ValueError("truncated discovery page must provide a continuation cursor")
        if self.source_version is not None and (
            not isinstance(self.source_version, str)
            or not self.source_version.strip()
            or len(self.source_version) > 256
        ):
            raise ValueError("discovery source_version must be non-empty text of at most 256 chars")


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


@dataclass(frozen=True, slots=True)
class ConnectorCommitResult:
    """Receipt for a connector sink operation using a caller-stable idempotency key."""

    idempotency_key: str
    commit_id: str
    output_id: str
    output_digest: str
    transactional: bool
    idempotency_enforced: bool
    delivery_semantics: Literal["at_least_once", "exactly_once"]

    def __post_init__(self) -> None:
        for name, value in (
            ("idempotency_key", self.idempotency_key),
            ("commit_id", self.commit_id),
            ("output_id", self.output_id),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"connector commit {name} must be non-empty trimmed text")
            if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
                raise ValueError(f"connector commit {name} must not contain control characters")
            if len(value.encode("utf-8")) > 1024:
                raise ValueError(f"connector commit {name} exceeds 1024 bytes")
        if not isinstance(self.output_digest, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", self.output_digest
        ):
            raise ValueError("connector commit output_digest must be a SHA-256 hex digest")
        if not isinstance(self.transactional, bool) or not isinstance(
            self.idempotency_enforced, bool
        ):
            raise ValueError("connector commit guarantees must be boolean")
        if self.delivery_semantics not in {"at_least_once", "exactly_once"}:
            raise ValueError("unsupported connector delivery semantics")
        if self.delivery_semantics == "exactly_once" and not self.idempotency_enforced:
            raise ValueError("exactly_once requires provider-enforced idempotency")


@runtime_checkable
class ConnectorWriter(Protocol):
    """Optional write capability. Every retry must reuse the same idempotency key."""

    def write(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        result: ConnectorReadResult,
        secrets: SecretResolver,
        *,
        idempotency_key: str,
    ) -> ConnectorCommitResult: ...


@runtime_checkable
class TransactionalConnectorWriter(ConnectorWriter, Protocol):
    """Optional stronger sink method advertised by transactional_write capability."""

    def transactional_write(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        result: ConnectorReadResult,
        secrets: SecretResolver,
        *,
        idempotency_key: str,
    ) -> ConnectorCommitResult: ...


class ConnectorCapabilityError(RuntimeError):
    """Raised when a connector cannot prove the requested write capability."""


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


__all__ = (
    "Connector",
    "ConnectorCapabilityError",
    "ConnectorCommitResult",
    "ConnectorReadResult",
    "ConnectorWriter",
    "DiscoveryPage",
    "PagedConnector",
    "TransactionalConnectorWriter",
)
