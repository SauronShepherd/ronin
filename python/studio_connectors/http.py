"""Provider-neutral HTTP adapter for bounded connector discovery and preview."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, cast

from studio_core import ConnectionDefinition
from studio_core.canonical_json import encode
from studio_storage.ports import ArtifactReferenceBarrier
from studio_storage.secrets import SecretResolver

from .registry import ConnectorRegistry
from .sync import IngestionSyncDefinition, IngestionSyncService


class _Health(Protocol):
    def to_payload(self) -> dict[str, object]: ...

    present: bool


class _CheckpointStore(Protocol):
    def health(self, identity: str) -> _Health: ...


class IngestionHTTPAdapter:
    def __init__(
        self,
        registry: ConnectorRegistry,
        checkpoints: object,
        connection_resolver: Callable[[str, str], ConnectionDefinition],
        asset_resolver: Callable[[str], object],
        secrets_resolver: Callable[[str], SecretResolver],
        *,
        artifact_reference_barrier: ArtifactReferenceBarrier | None = None,
    ) -> None:
        self._registry = registry
        self._service = IngestionSyncService(
            registry, checkpoints, artifact_reference_barrier=artifact_reference_barrier
        )
        self._checkpoints = cast(_CheckpointStore, checkpoints)
        self._connection = connection_resolver
        self._asset = asset_resolver
        self._secrets = secrets_resolver

    def capabilities(self) -> dict[str, object]:
        return self._registry.capability_payload()

    def discover(self, body: object, *, workspace_id: str) -> dict[str, object]:
        if not isinstance(body, Mapping) or set(body) != {"connector_id", "connection_ref"}:
            raise ValueError(
                "connector discovery body must contain connector_id and connection_ref"
            )
        connector_id = body["connector_id"]
        connection_ref = body["connection_ref"]
        if not isinstance(connector_id, str) or not connector_id.strip():
            raise ValueError("connector_id must be non-empty text")
        if not isinstance(connection_ref, str) or not connection_ref.strip():
            raise ValueError("connection_ref must be non-empty text")
        connector = self._registry.require(connector_id)
        connection = self._connection(workspace_id, connection_ref)
        if getattr(connection, "connector_id", connector_id) != connector_id:
            raise ValueError("connection connector_id does not match connector_id")
        assets = connector.discover(connection, self._secrets(connection_ref))
        items = [
            {
                "asset_ref": (f"{asset.handle.connection_id}::{asset.handle.qualified_name}"),
                "kind": asset.kind,
                "fields": [
                    {"name": field.name, "data_type": field.data_type, "nullable": field.nullable}
                    for field in asset.fields
                ],
            }
            for asset in assets
        ]
        return {"schema": "ronin.connector-discovery/v1", "items": items, "count": len(items)}

    def preview(self, body: object, *, workspace_id: str) -> dict[str, object]:
        definition = self._definition(body)
        return self._service.preview(
            definition,
            connection=self._connection(workspace_id, definition.connection_ref),
            asset=self._asset(definition.asset_ref),
            secrets=self._secrets(definition.connection_ref),
            checkpoint_identity=self._checkpoint_identity(
                workspace_id, definition.checkpoint_identity
            ),
        )

    def plan(self, body: object, *, workspace_id: str) -> dict[str, object]:
        definition = self._definition(body)
        checkpoint = self._checkpoint_health(workspace_id, definition.checkpoint_identity)
        plan = self._registry.plan_sync(definition, checkpoint_present=bool(checkpoint["present"]))
        return {"plan": plan.to_payload(), "checkpoint": checkpoint}

    def checkpoint_health(self, body: object, *, workspace_id: str) -> dict[str, object]:
        if not isinstance(body, Mapping) or set(body) != {"checkpoint_identity"}:
            raise ValueError("checkpoint health body must contain checkpoint_identity")
        identity = body["checkpoint_identity"]
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("checkpoint_identity must be non-empty text")
        return self._checkpoint_health(workspace_id, identity)

    def _checkpoint_health(self, workspace_id: str, identity: str) -> dict[str, object]:
        checkpoint = self._checkpoints.health(self._checkpoint_identity(workspace_id, identity))
        payload = cast(dict[str, object], checkpoint.to_payload())
        payload["identity"] = identity
        return payload

    @staticmethod
    def _checkpoint_identity(workspace_id: str, identity: str) -> str:
        if not workspace_id.strip():
            raise ValueError("workspace_id must be non-empty text")
        return f"{workspace_id}/{identity}"

    @staticmethod
    def _definition(body: object) -> IngestionSyncDefinition:
        if not isinstance(body, Mapping):
            raise ValueError("ingestion sync body must be an object")
        expected = {
            "id",
            "connector_id",
            "connection_ref",
            "asset_ref",
            "destination_ref",
            "checkpoint_identity",
            "mode",
        }
        if set(body) != expected:
            raise ValueError("ingestion sync body has invalid fields")
        canonical_body = {"schema": "ronin.ingestion-sync/v1", **dict(body)}
        return IngestionSyncDefinition.from_bytes(encode(canonical_body))


__all__ = ("IngestionHTTPAdapter",)
