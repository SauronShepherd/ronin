"""Provider-neutral HTTP adapter for bounded connector discovery and preview."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, cast

from studio_core.canonical_json import encode

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
        connection_resolver: Callable[[str], object],
        asset_resolver: Callable[[str], object],
        secrets_resolver: Callable[[str], object],
    ) -> None:
        self._registry = registry
        self._service = IngestionSyncService(registry, checkpoints)
        self._checkpoints = cast(_CheckpointStore, checkpoints)
        self._connection = connection_resolver
        self._asset = asset_resolver
        self._secrets = secrets_resolver

    def capabilities(self) -> dict[str, object]:
        return self._registry.capability_payload()

    def preview(self, body: object) -> dict[str, object]:
        definition = self._definition(body)
        return self._service.preview(
            definition,
            connection=self._connection(definition.connection_ref),
            asset=self._asset(definition.asset_ref),
            secrets=self._secrets(definition.connection_ref),
        )

    def plan(self, body: object) -> dict[str, object]:
        definition = self._definition(body)
        health = self._checkpoints.health(definition.checkpoint_identity)
        plan = self._registry.plan_sync(definition, checkpoint_present=health.present)
        return {"plan": plan.to_payload(), "checkpoint": health.to_payload()}

    def checkpoint_health(self, body: object) -> dict[str, object]:
        if not isinstance(body, Mapping) or set(body) != {"checkpoint_identity"}:
            raise ValueError("checkpoint health body must contain checkpoint_identity")
        identity = body["checkpoint_identity"]
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("checkpoint_identity must be non-empty text")
        return cast(dict[str, object], self._checkpoints.health(identity).to_payload())

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
