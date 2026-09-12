"""Provider-neutral connection, discovery, and incremental-ingestion contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urlsplit

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json

CheckpointStrategy = Literal["cursor", "watermark", "snapshot"]

_SENSITIVE_KEY_TERMS = (
    "password",
    "secret",
    "token",
    "credential",
    "api_key",
    "api-key",
    "access_key",
    "access-key",
    "private_key",
    "private-key",
)


def _require_text(value: str, field_name: str) -> str:
    if not value or value.strip() != value or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{field_name} must be non-empty, trimmed, and single-line")
    return value


def _require_safe_option_key(value: str) -> str:
    value = _require_text(value, "connection option key")
    folded = value.casefold()
    if any(term in folded for term in _SENSITIVE_KEY_TERMS):
        raise ValueError("secret-bearing connection settings must use secret_refs")
    return value


@dataclass(frozen=True, order=True, slots=True)
class ConnectionId:
    """Stable logical connection identity independent of credentials or deployment."""

    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "connection id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class SecretRef:
    """Opaque secret reference. Plaintext secret material is never represented here."""

    uri: str

    def __post_init__(self) -> None:
        _require_text(self.uri, "secret reference")
        parsed = urlsplit(self.uri)
        if parsed.scheme != "secret":
            raise ValueError("secret reference must use secret://")
        if not parsed.netloc and not parsed.path:
            raise ValueError("secret reference must identify a secret")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("secret reference must not embed credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("secret reference must not contain query or fragment components")

    def __str__(self) -> str:
        return self.uri


@dataclass(frozen=True, slots=True)
class ConnectorCapabilities:
    discover: bool = False
    read: bool = False
    write: bool = False
    incremental: bool = False
    stream: bool = False
    transactional_write: bool = False

    def __post_init__(self) -> None:
        if self.incremental and not self.read:
            raise ValueError("incremental capability requires read capability")
        if self.transactional_write and not self.write:
            raise ValueError("transactional_write capability requires write capability")


@dataclass(frozen=True, slots=True)
class ConnectorDescriptor:
    """Versioned connector identity and advertised portable capabilities."""

    connector_id: str
    contract_version: int
    capabilities: ConnectorCapabilities

    def __post_init__(self) -> None:
        _require_text(self.connector_id, "connector id")
        if self.contract_version < 1:
            raise ValueError("connector contract version must be positive")


@dataclass(frozen=True, order=True, slots=True)
class FieldSchema:
    name: str
    data_type: str
    nullable: bool = True

    def __post_init__(self) -> None:
        _require_text(self.name, "field name")
        _require_text(self.data_type, "field data type")


@dataclass(frozen=True, order=True, slots=True)
class AssetHandle:
    """Connection-relative source/sink asset handle with no credential-bearing locator."""

    connection_id: ConnectionId
    namespace: tuple[str, ...]
    name: str

    def __post_init__(self) -> None:
        _require_text(self.name, "asset name")
        for part in self.namespace:
            _require_text(part, "asset namespace component")

    @property
    def qualified_name(self) -> str:
        return ".".join((*self.namespace, self.name))


@dataclass(frozen=True, slots=True)
class DiscoveredAsset:
    handle: AssetHandle
    kind: str
    fields: tuple[FieldSchema, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.kind, "discovered asset kind")
        canonical_fields = tuple(sorted(self.fields, key=lambda field: field.name))
        names = [field.name for field in canonical_fields]
        if len(names) != len(set(names)):
            raise ValueError("discovered asset field names must be unique")
        object.__setattr__(self, "fields", canonical_fields)


@dataclass(frozen=True, order=True, slots=True)
class SourceCheckpoint:
    """Committed connector checkpoint advanced only after sink/output commit."""

    strategy: CheckpointStrategy
    value: str

    def __post_init__(self) -> None:
        if self.strategy not in {"cursor", "watermark", "snapshot"}:
            raise ValueError("unsupported checkpoint strategy")
        _require_text(self.value, "checkpoint value")


@dataclass(frozen=True, slots=True)
class ConnectionDefinition:
    """Portable connection intent with non-secret options and secret references separated."""

    id: ConnectionId
    name: str
    connector_id: str
    options: tuple[tuple[str, str], ...] = ()
    secret_refs: tuple[tuple[str, SecretRef], ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.name, "connection name")
        _require_text(self.connector_id, "connector id")

        options: list[tuple[str, str]] = []
        option_keys: set[str] = set()
        for key, value in self.options:
            key = _require_safe_option_key(key)
            value = _require_text(value, "connection option value")
            if key in option_keys:
                raise ValueError("connection option keys must be unique")
            option_keys.add(key)
            options.append((key, value))

        refs: list[tuple[str, SecretRef]] = []
        ref_keys: set[str] = set()
        for key, ref in self.secret_refs:
            key = _require_text(key, "connection secret binding key")
            if key in ref_keys:
                raise ValueError("connection secret binding keys must be unique")
            if key in option_keys:
                raise ValueError("connection key cannot appear in both options and secret_refs")
            ref_keys.add(key)
            refs.append((key, ref))

        object.__setattr__(self, "options", tuple(sorted(options)))
        object.__setattr__(self, "secret_refs", tuple(sorted(refs, key=lambda item: item[0])))

    def to_payload(self) -> dict[str, object]:
        return {
            "connector_id": self.connector_id,
            "id": self.id.value,
            "name": self.name,
            "options": dict(self.options),
            "secret_refs": {key: ref.uri for key, ref in self.secret_refs},
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> ConnectionDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "connector_id",
            "id",
            "name",
            "options",
            "secret_refs",
        }:
            raise ValueError("connection payload has invalid shape")
        options = payload["options"]
        secret_refs = payload["secret_refs"]
        if not isinstance(options, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in options.items()
        ):
            raise ValueError("connection options must be a string object")
        if not isinstance(secret_refs, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in secret_refs.items()
        ):
            raise ValueError("connection secret_refs must be a string object")
        identifier = payload["id"]
        name = payload["name"]
        connector_id = payload["connector_id"]
        if not all(isinstance(value, str) for value in (identifier, name, connector_id)):
            raise ValueError("connection id, name, and connector_id must be strings")
        return cls(
            id=ConnectionId(cast(str, identifier)),
            name=cast(str, name),
            connector_id=cast(str, connector_id),
            options=tuple(sorted(cast(Mapping[str, str], options).items())),
            secret_refs=tuple(
                sorted(
                    (key, SecretRef(value))
                    for key, value in cast(Mapping[str, str], secret_refs).items()
                )
            ),
        )

    @classmethod
    def from_json(cls, payload: str) -> ConnectionDefinition:
        return cls.from_payload(decode_canonical_json(payload))


def discovered_assets_payload(assets: Sequence[DiscoveredAsset]) -> list[dict[str, object]]:
    """Return a deterministic public discovery payload suitable for API/evidence boundaries."""

    ordered = sorted(assets, key=lambda asset: (asset.handle.qualified_name, asset.kind))
    return [
        {
            "connection_id": asset.handle.connection_id.value,
            "namespace": list(asset.handle.namespace),
            "name": asset.handle.name,
            "kind": asset.kind,
            "fields": [
                {"name": field.name, "data_type": field.data_type, "nullable": field.nullable}
                for field in asset.fields
            ],
        }
        for asset in ordered
    ]
