"""Versioned, provider-neutral ingestion sync definitions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, cast

from studio_core.canonical_json import decode, encode

from .contracts import ConnectorReadResult


class ArtifactDestinationWriter:
    """Write connector rows as one verified content-addressed JSON artifact."""

    def __init__(self, artifacts: object) -> None:
        self._artifacts = artifacts

    def write(
        self,
        destination_ref: str,
        result: ConnectorReadResult,
        *,
        fence: int,
    ) -> tuple[str, str]:
        if not destination_ref or destination_ref != destination_ref.strip():
            raise ValueError("destination_ref must be non-empty and trimmed")
        if fence < 1:
            raise ValueError("destination fence must be positive")
        payload = json.dumps(
            {
                "schema": "ronin.connector-output/v1",
                "destination_ref": destination_ref,
                "fence": fence,
                "fields": [
                    {"name": field.name, "data_type": field.data_type, "nullable": field.nullable}
                    for field in result.fields
                ],
                "rows": [dict(row) for row in result.rows],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        ref = self._artifacts.put_bytes(
            role="connector-output",
            data=payload,
            media_type="application/vnd.ronin.connector-output+json",
        )
        return ref.storage_ref, ref.digest


class _CheckpointStore(Protocol):
    def health(self, identity: str) -> _Health: ...


class _Health(Protocol):
    present: bool

    def to_payload(self) -> dict[str, object]: ...


class _SyncRegistry(Protocol):
    def plan_sync(
        self, definition: IngestionSyncDefinition, *, checkpoint_present: bool
    ) -> IngestionSyncPlan: ...
    def preview(
        self,
        connector_id: str,
        connection: object,
        asset: object,
        secrets: object,
        *,
        limit: int = 100,
    ) -> ConnectorReadResult: ...
    def read(
        self,
        connector_id: str,
        connection: object,
        asset: object,
        secrets: object,
        *,
        limit: int = 10_000,
        checkpoint: object | None = None,
    ) -> ConnectorReadResult: ...


class _DestinationWriter(Protocol):
    def write(
        self,
        destination_ref: str,
        result: ConnectorReadResult,
        *,
        fence: int,
    ) -> tuple[str, str]: ...


@dataclass(frozen=True, slots=True)
class IngestionSyncPlan:
    definition_id: str
    connector_id: str
    mode: str
    checkpoint_identity: str
    requires_checkpoint: bool
    bounded: bool = True

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode(self._payload())).hexdigest()

    def _payload(self) -> dict[str, object]:
        return {
            "schema": "ronin.ingestion-sync-plan/v1",
            "definition_id": self.definition_id,
            "connector_id": self.connector_id,
            "mode": self.mode,
            "checkpoint_identity": self.checkpoint_identity,
            "requires_checkpoint": self.requires_checkpoint,
            "bounded": self.bounded,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self._payload(), "digest": self.digest}


def plan_sync(
    definition: IngestionSyncDefinition,
    *,
    incremental_capable: bool,
    checkpoint_present: bool,
) -> IngestionSyncPlan:
    """Build a bounded sync plan, refusing unsupported incremental semantics."""

    if definition.mode == "incremental" and not incremental_capable:
        raise ValueError("connector does not advertise incremental capability")
    if definition.mode == "incremental" and not checkpoint_present:
        raise ValueError("incremental sync requires an existing checkpoint")
    return IngestionSyncPlan(
        definition.id,
        definition.connector_id,
        definition.mode,
        definition.checkpoint_identity,
        definition.mode == "incremental",
    )


@dataclass(frozen=True, slots=True)
class IngestionSyncDefinition:
    id: str
    connector_id: str
    connection_ref: str
    asset_ref: str
    destination_ref: str
    checkpoint_identity: str
    mode: str = "snapshot"
    schema: str = "ronin.ingestion-sync/v1"

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "sync id"),
            (self.connector_id, "connector id"),
            (self.connection_ref, "connection ref"),
            (self.asset_ref, "asset ref"),
            (self.destination_ref, "destination ref"),
            (self.checkpoint_identity, "checkpoint identity"),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be non-empty and trimmed")
        if self.mode not in {"snapshot", "incremental"}:
            raise ValueError("sync mode must be snapshot or incremental")
        if self.schema != "ronin.ingestion-sync/v1":
            raise ValueError("unsupported ingestion sync schema")

    def to_payload(self) -> dict[str, str]:
        return {
            "schema": self.schema,
            "id": self.id,
            "connector_id": self.connector_id,
            "connection_ref": self.connection_ref,
            "asset_ref": self.asset_ref,
            "destination_ref": self.destination_ref,
            "checkpoint_identity": self.checkpoint_identity,
            "mode": self.mode,
        }

    def to_bytes(self) -> bytes:
        return encode(self.to_payload())

    @classmethod
    def from_bytes(cls, payload: bytes) -> IngestionSyncDefinition:
        value = decode(payload)
        expected = {
            "schema",
            "id",
            "connector_id",
            "connection_ref",
            "asset_ref",
            "destination_ref",
            "checkpoint_identity",
            "mode",
        }
        if (
            not isinstance(value, dict)
            or set(value) != expected
            or not all(isinstance(value[key], str) for key in expected)
        ):
            raise ValueError("ingestion sync definition has invalid shape")
        return cls(**cast(dict[str, str], value))


class IngestionSyncService:
    """Bounded preview service; destination writes remain an explicit next step."""

    def __init__(self, registry: object, checkpoints: object) -> None:
        self._registry = cast(_SyncRegistry, registry)
        self._checkpoints = cast(_CheckpointStore, checkpoints)

    def preview(
        self,
        definition: IngestionSyncDefinition,
        *,
        connection: object,
        asset: object,
        secrets: object,
        limit: int = 100,
    ) -> dict[str, object]:
        health = self._checkpoints.health(definition.checkpoint_identity)
        plan = self._registry.plan_sync(definition, checkpoint_present=health.present)
        result = self._registry.preview(
            definition.connector_id, connection, asset, secrets, limit=limit
        )
        return {
            "schema": "ronin.ingestion-preview/v1",
            "plan": plan.to_payload(),
            "plan_digest": plan.digest,
            "fields": [
                {"name": field.name, "data_type": field.data_type, "nullable": field.nullable}
                for field in result.fields
            ],
            "rows": [dict(row) for row in result.rows],
            "row_count": len(result.rows),
            "checkpoint": health.to_payload(),
        }

    def execute(
        self,
        definition: IngestionSyncDefinition,
        *,
        connection: object,
        asset: object,
        secrets: object,
        destination: _DestinationWriter,
        limit: int = 10_000,
    ) -> dict[str, object]:
        """Read, durably write the destination, then advance the checkpoint."""

        health = self._checkpoints.health(definition.checkpoint_identity)
        expected = self._checkpoints.get(definition.checkpoint_identity)
        plan = self._registry.plan_sync(definition, checkpoint_present=health.present)
        fence = self._checkpoints.acquire(definition.checkpoint_identity)
        result = self._registry.read(
            definition.connector_id,
            connection,
            asset,
            secrets,
            limit=limit,
            checkpoint=expected,
        )
        if result.checkpoint is None:
            raise ValueError("connector sync execution must return a next checkpoint")
        output_id, output_digest = destination.write(
            definition.destination_ref,
            result,
            fence=fence,
        )
        evidence = self._checkpoints.commit_output_then_checkpoint(
            definition.checkpoint_identity,
            expected,
            result.checkpoint,
            output_id=output_id,
            output_digest=output_digest,
            fence=fence,
            output_committed=True,
        )
        return {
            "schema": "ronin.ingestion-sync-result/v1",
            "plan": plan.to_payload(),
            "rows_written": len(result.rows),
            "checkpoint": evidence.to_payload(),
        }


__all__ = (
    "ArtifactDestinationWriter",
    "IngestionSyncDefinition",
    "IngestionSyncPlan",
    "IngestionSyncService",
    "plan_sync",
)
