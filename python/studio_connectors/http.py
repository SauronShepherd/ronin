"""Provider-neutral HTTP adapter for bounded connector discovery and preview."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from studio_core import ConnectionDefinition
from studio_core.canonical_json import decode, encode
from studio_storage.ports import ArtifactReferenceBarrier
from studio_storage.secrets import SecretResolver

from .registry import ConnectorRegistry
from .sync import IngestionSyncDefinition, IngestionSyncService, scoped_checkpoint_identity


class _Health(Protocol):
    def to_payload(self) -> dict[str, object]: ...

    present: bool


class _CheckpointStore(Protocol):
    def health(self, identity: str) -> _Health: ...


class IngestionHTTPAdapter:
    _CURSOR_SCHEMA = "ronin.connector-discovery-cursor/v1"
    _MAX_CURSOR_LENGTH = 16_384

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
        required = {"connector_id", "connection_ref"}
        optional = {"cursor", "page_size"}
        if (
            not isinstance(body, Mapping)
            or not required.issubset(body)
            or set(body) - required - optional
        ):
            raise ValueError("connector discovery body has invalid fields")
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
        secrets = self._secrets(connection_ref)
        cursor_value = body.get("cursor")
        page_size_value = body.get("page_size")
        if cursor_value is not None and (
            not isinstance(cursor_value, str)
            or not cursor_value
            or len(cursor_value) > self._MAX_CURSOR_LENGTH
        ):
            raise ValueError("connector discovery cursor is invalid")
        if page_size_value is not None and (
            not isinstance(page_size_value, int) or isinstance(page_size_value, bool)
        ):
            raise ValueError("connector discovery page_size must be an integer")

        discover_page = getattr(connector, "discover_page", None)
        if not connector.descriptor.capabilities.discover:
            raise ValueError("connector does not advertise discovery capability")
        if not callable(discover_page):
            raise ValueError("connector does not provide bounded paginated discovery")
        max_page_size = connector.descriptor.capabilities.max_page_size or 1000
        page_size = page_size_value if page_size_value is not None else min(1000, max_page_size)
        if page_size < 1 or page_size > min(10_000, max_page_size):
            raise ValueError(
                "connector discovery page_size exceeds the connector's advertised limit"
            )
        provider_cursor = self._decode_discovery_cursor(
            cursor_value,
            workspace_id=workspace_id,
            connector_id=connector_id,
            connection_ref=connection_ref,
            connection_id=str(connection.id),
        )
        page = discover_page(
            connection,
            secrets,
            cursor=provider_cursor,
            page_size=page_size,
        )
        if len(page.items) > page_size:
            raise ValueError("connector discovery page exceeded the requested page_size")
        if provider_cursor is not None and page.next_cursor == provider_cursor:
            raise ValueError("connector discovery cursor did not advance")
        assets = page.items
        next_cursor = (
            self._encode_discovery_cursor(
                page.next_cursor,
                workspace_id=workspace_id,
                connector_id=connector_id,
                connection_ref=connection_ref,
                connection_id=str(connection.id),
            )
            if page.truncated and page.next_cursor is not None
            else None
        )
        page_metadata: dict[str, object] = {
            "has_more": page.truncated,
            "next_cursor": next_cursor,
        }
        if page.source_version is not None:
            page_metadata["source_version"] = page.source_version
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
        return {
            "schema": "ronin.connector-discovery/v1",
            "items": items,
            "count": len(items),
            **page_metadata,
        }

    @classmethod
    def _encode_discovery_cursor(
        cls,
        provider_cursor: str,
        *,
        workspace_id: str,
        connector_id: str,
        connection_ref: str,
        connection_id: str,
    ) -> str:
        payload = encode(
            {
                "schema": cls._CURSOR_SCHEMA,
                "workspace_id": workspace_id,
                "connector_id": connector_id,
                "connection_ref": connection_ref,
                "connection_id": connection_id,
                "provider_cursor": provider_cursor,
            }
        )
        cursor = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        if len(cursor) > cls._MAX_CURSOR_LENGTH:
            raise ValueError("connector discovery cursor is too large")
        return cursor

    @classmethod
    def _decode_discovery_cursor(
        cls,
        cursor: str | None,
        *,
        workspace_id: str,
        connector_id: str,
        connection_ref: str,
        connection_id: str,
    ) -> str | None:
        if cursor is None:
            return None
        if len(cursor) > cls._MAX_CURSOR_LENGTH:
            raise ValueError("connector discovery cursor is too large")
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
            payload = decode(raw)
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise ValueError("connector discovery cursor is invalid") from exc
        expected = {
            "schema": cls._CURSOR_SCHEMA,
            "workspace_id": workspace_id,
            "connector_id": connector_id,
            "connection_ref": connection_ref,
            "connection_id": connection_id,
        }
        if not isinstance(payload, dict) or any(
            payload.get(key) != value for key, value in expected.items()
        ):
            raise ValueError("connector discovery cursor belongs to a different source scope")
        if set(payload) != {*expected, "provider_cursor"}:
            raise ValueError("connector discovery cursor is invalid")
        provider_cursor = payload["provider_cursor"]
        if not isinstance(provider_cursor, str) or not provider_cursor:
            raise ValueError("connector discovery cursor is invalid")
        return provider_cursor

    def preview(self, body: object, *, workspace_id: str) -> dict[str, object]:
        definition = self._definition(body)
        return self._service.preview(
            definition,
            workspace_id=workspace_id,
            connection=self._connection(workspace_id, definition.connection_ref),
            asset=self._asset(definition.asset_ref),
            secrets=self._secrets(definition.connection_ref),
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
        return scoped_checkpoint_identity(workspace_id, identity)

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
