"""Provider-neutral executable connector registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from studio_core import AssetHandle, ConnectionDefinition, ConnectorCapabilities
from studio_storage.secrets import SecretResolver

from .contracts import Connector, ConnectorReadResult
from .sync import IngestionSyncDefinition, IngestionSyncPlan, plan_sync


@dataclass(frozen=True, slots=True)
class ConnectorCapabilityRecord:
    """Stable registry projection used by planners and Studio surfaces."""

    connector_id: str
    contract_version: int
    capabilities: ConnectorCapabilities

    def to_payload(self) -> dict[str, object]:
        """Return a stable, provider-neutral discovery payload for API/UI consumers."""
        capabilities = self.capabilities
        return {
            "connector_id": self.connector_id,
            "contract_version": self.contract_version,
            "capabilities": {
                "discover": capabilities.discover,
                "read": capabilities.read,
                "write": capabilities.write,
                "incremental": capabilities.incremental,
                "stream": capabilities.stream,
                "transactional_write": capabilities.transactional_write,
                "schema": capabilities.schema,
                "predicate_pushdown": capabilities.predicate_pushdown,
                "watermark_types": list(capabilities.watermark_types),
                "auth_modes": list(capabilities.auth_modes),
                "lineage": capabilities.lineage,
                "max_page_size": capabilities.max_page_size,
                "max_batch_size": capabilities.max_batch_size,
            },
        }

    @classmethod
    def from_payload(cls, value: object) -> ConnectorCapabilityRecord:
        """Validate a wire capability record without guessing omitted values."""
        if not isinstance(value, dict) or set(value) != {
            "connector_id",
            "contract_version",
            "capabilities",
        }:
            raise ValueError("connector capability record has an invalid shape")
        connector_id = value["connector_id"]
        version = value["contract_version"]
        raw = value["capabilities"]
        if not isinstance(connector_id, str) or not connector_id.strip():
            raise ValueError("connector_id must be non-empty text")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("contract_version must be a positive integer")
        if not isinstance(raw, dict):
            raise ValueError("capabilities must be an object")
        expected = {
            "discover",
            "read",
            "write",
            "incremental",
            "stream",
            "transactional_write",
            "schema",
            "predicate_pushdown",
            "watermark_types",
            "auth_modes",
            "lineage",
            "max_page_size",
            "max_batch_size",
        }
        if set(raw) != expected:
            raise ValueError("capability fields mismatch")
        booleans = expected - {"watermark_types", "auth_modes", "max_page_size", "max_batch_size"}
        if any(not isinstance(raw[key], bool) for key in booleans):
            raise ValueError("connector boolean capabilities must be boolean")
        for key in ("watermark_types", "auth_modes"):
            if not isinstance(raw[key], list) or not all(
                isinstance(item, str) for item in raw[key]
            ):
                raise ValueError(f"{key} must be a string array")
        for key in ("max_page_size", "max_batch_size"):
            if raw[key] is not None and (
                not isinstance(raw[key], int) or isinstance(raw[key], bool) or raw[key] < 1
            ):
                raise ValueError(f"{key} must be null or a positive integer")
        capabilities = ConnectorCapabilities(
            discover=raw["discover"],
            read=raw["read"],
            write=raw["write"],
            incremental=raw["incremental"],
            stream=raw["stream"],
            transactional_write=raw["transactional_write"],
            schema=raw["schema"],
            predicate_pushdown=raw["predicate_pushdown"],
            watermark_types=tuple(raw["watermark_types"]),
            auth_modes=tuple(raw["auth_modes"]),
            lineage=raw["lineage"],
            max_page_size=raw["max_page_size"],
            max_batch_size=raw["max_batch_size"],
        )
        return cls(connector_id, version, capabilities)


class ConnectorRegistry:
    """Resolve executable connectors by stable connector_id without fallback guessing."""

    def __init__(self, connectors: Iterable[Connector] = ()) -> None:
        by_id: dict[str, Connector] = {}
        for connector in connectors:
            connector_id = connector.descriptor.connector_id
            if connector_id in by_id:
                raise ValueError(f"duplicate executable connector id: {connector_id}")
            by_id[connector_id] = connector
        self._by_id = by_id

    def get(self, connector_id: str) -> Connector | None:
        return self._by_id.get(connector_id)

    def require(self, connector_id: str) -> Connector:
        connector = self.get(connector_id)
        if connector is None:
            raise KeyError(f"no executable connector registered: {connector_id}")
        return connector

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))

    def capability_records(self) -> tuple[ConnectorCapabilityRecord, ...]:
        return tuple(
            ConnectorCapabilityRecord(
                connector_id=connector_id,
                contract_version=self._by_id[connector_id].descriptor.contract_version,
                capabilities=self._by_id[connector_id].descriptor.capabilities,
            )
            for connector_id in self.ids()
        )

    def capability_payload(self) -> dict[str, object]:
        """Expose deterministic connector capability discovery for adapters and Studio."""
        return {
            "items": [record.to_payload() for record in self.capability_records()],
            "count": len(self._by_id),
        }

    def preview(
        self,
        connector_id: str,
        connection: object,
        asset: object,
        secrets: object,
        *,
        limit: int = 100,
    ) -> ConnectorReadResult:
        """Read a bounded preview only from connectors advertising read support."""

        if limit < 1 or limit > 10_000:
            raise ValueError("connector preview limit must be between 1 and 10000")
        connector = self.require(connector_id)
        if not connector.descriptor.capabilities.read:
            raise ValueError(f"connector does not advertise read capability: {connector_id}")
        result = connector.read(
            cast(ConnectionDefinition, connection),
            cast(AssetHandle, asset),
            cast(SecretResolver, secrets),
            limit=limit,
        )
        if not isinstance(result, ConnectorReadResult):
            raise TypeError("connector read must return ConnectorReadResult")
        return result

    def plan_sync(
        self, definition: IngestionSyncDefinition, *, checkpoint_present: bool
    ) -> IngestionSyncPlan:
        """Plan sync using the registered connector's authoritative capabilities."""

        connector = self.require(definition.connector_id)
        return plan_sync(
            definition,
            incremental_capable=connector.descriptor.capabilities.incremental,
            checkpoint_present=checkpoint_present,
        )


def builtin_connector_registry() -> ConnectorRegistry:
    """Return the explicit reference connector set shipped with Ronin."""

    from .azure_blob_json import AzureBlobJsonConnector
    from .http_json import HttpJsonConnector
    from .jdbc import JdbcConnector
    from .ozone import OzoneJsonConnector
    from .postgres import PostgresConnector
    from .s3_json import S3JsonConnector

    return ConnectorRegistry(
        (
            AzureBlobJsonConnector(),
            HttpJsonConnector(),
            JdbcConnector(),
            OzoneJsonConnector(),
            PostgresConnector(),
            S3JsonConnector(),
        )
    )


__all__ = ("ConnectorCapabilityRecord", "ConnectorRegistry", "builtin_connector_registry")
