"""Versioned, provider-neutral ingestion sync definitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Protocol, cast

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    LineageEdge,
    SourceCheckpoint,
    WorkspaceId,
)
from studio_core.canonical_json import decode, encode
from studio_storage.ports import ArtifactReferenceBarrier

from .contracts import ConnectorReadResult


class IngestionSyncCancelled(RuntimeError):
    """Raised when a durable sync is cancelled before its output/checkpoint commit."""


def scoped_checkpoint_identity(workspace_id: str, identity: str) -> str:
    """Return a stable checkpoint key that cannot alias across workspace scopes."""
    if (
        not isinstance(workspace_id, str)
        or not workspace_id
        or workspace_id != workspace_id.strip()
        or not isinstance(identity, str)
        or not identity
        or identity != identity.strip()
    ):
        raise ValueError("workspace_id and checkpoint identity must be non-empty and trimmed")
    if "/" not in workspace_id and "/" not in identity:
        # Preserve unambiguous legacy keys so existing checkpoint rows remain readable.
        return f"{workspace_id}/{identity}"
    identity_bytes = encode({"workspace_id": workspace_id, "identity": identity})
    return f"ronin:v2:{hashlib.sha256(identity_bytes).hexdigest()}"


class ArtifactDestinationWriter:
    """Write connector rows as one verified content-addressed JSON artifact."""

    def __init__(self, artifacts: _ArtifactStore) -> None:
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

    def get(self, identity: str) -> SourceCheckpoint | None: ...

    def acquire(self, identity: str) -> int: ...

    def commit_output_then_checkpoint(
        self,
        identity: str,
        expected: SourceCheckpoint | None,
        next_checkpoint: SourceCheckpoint,
        *,
        output_id: str,
        output_digest: str,
        fence: int,
        output_committed: bool,
        catalog_commit: tuple[
            WorkspaceId,
            AssetRevision,
            LineageEdge,
            str,
            tuple[str, str, str],
        ]
        | None = None,
    ) -> _Evidence: ...


class _ArtifactRef(Protocol):
    @property
    def storage_ref(self) -> str: ...

    @property
    def digest(self) -> str: ...


class _ArtifactStore(Protocol):
    def put_bytes(
        self, *, role: str, data: bytes, media_type: str | None = None
    ) -> _ArtifactRef: ...


class _Evidence(Protocol):
    def to_payload(self) -> dict[str, object]: ...


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
        checkpoint: SourceCheckpoint | None = None,
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
    source_revision_ref: AssetRef | None = None
    destination_asset_id: AssetId | None = None

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
        if (self.source_revision_ref is None) != (self.destination_asset_id is None):
            raise ValueError(
                "governed sync requires both source_revision_ref and destination_asset_id"
            )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": self.schema,
            "id": self.id,
            "connector_id": self.connector_id,
            "connection_ref": self.connection_ref,
            "asset_ref": self.asset_ref,
            "destination_ref": self.destination_ref,
            "checkpoint_identity": self.checkpoint_identity,
            "mode": self.mode,
        }
        if self.source_revision_ref is not None and self.destination_asset_id is not None:
            payload["source_revision_ref"] = self.source_revision_ref.to_payload()
            payload["destination_asset_id"] = self.destination_asset_id.value
        return payload

    def to_bytes(self) -> bytes:
        return cast(bytes, encode(self.to_payload()))

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
        if not isinstance(value, dict) or frozenset(value) not in {
            frozenset(expected),
            frozenset(expected | {"source_revision_ref", "destination_asset_id"}),
        }:
            raise ValueError("ingestion sync definition has invalid shape")
        if not all(isinstance(value[key], str) for key in expected):
            raise ValueError("ingestion sync definition has invalid shape")
        values = cast(dict[str, object], value)
        source_ref_value = values.get("source_revision_ref")
        destination_asset_value = values.get("destination_asset_id")
        if source_ref_value is not None:
            values["source_revision_ref"] = AssetRef.from_payload(source_ref_value)
        if destination_asset_value is not None:
            if not isinstance(destination_asset_value, str):
                raise ValueError("destination_asset_id must be text")
            values["destination_asset_id"] = AssetId(destination_asset_value)
        return cls(
            id=cast(str, values["id"]),
            connector_id=cast(str, values["connector_id"]),
            connection_ref=cast(str, values["connection_ref"]),
            asset_ref=cast(str, values["asset_ref"]),
            destination_ref=cast(str, values["destination_ref"]),
            checkpoint_identity=cast(str, values["checkpoint_identity"]),
            mode=cast(str, values["mode"]),
            schema=cast(str, values["schema"]),
            source_revision_ref=cast(AssetRef | None, values.get("source_revision_ref")),
            destination_asset_id=cast(AssetId | None, values.get("destination_asset_id")),
        )


class IngestionSyncService:
    """Build bounded previews and commit sync output before advancing checkpoints."""

    def __init__(
        self,
        registry: object,
        checkpoints: object,
        *,
        artifact_reference_barrier: ArtifactReferenceBarrier | None = None,
    ) -> None:
        self._registry = cast(_SyncRegistry, registry)
        self._checkpoints = cast(_CheckpointStore, checkpoints)
        self._artifact_reference_barrier = artifact_reference_barrier

    def _writer_lease(self) -> AbstractContextManager[None]:
        if self._artifact_reference_barrier is None:
            return cast(AbstractContextManager[None], nullcontext())
        return cast(AbstractContextManager[None], self._artifact_reference_barrier.writer())

    def preview(
        self,
        definition: IngestionSyncDefinition,
        *,
        workspace_id: str,
        connection: object,
        asset: object,
        secrets: object,
        limit: int = 100,
    ) -> dict[str, object]:
        scoped_identity = scoped_checkpoint_identity(workspace_id, definition.checkpoint_identity)
        health = self._checkpoints.health(scoped_identity)
        plan = self._registry.plan_sync(definition, checkpoint_present=health.present)
        result = self._registry.preview(
            definition.connector_id, connection, asset, secrets, limit=limit
        )
        checkpoint = health.to_payload()
        checkpoint["identity"] = definition.checkpoint_identity
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
            "checkpoint": checkpoint,
        }

    def execute(
        self,
        definition: IngestionSyncDefinition,
        *,
        workspace_id: str,
        connection: object,
        asset: object,
        secrets: object,
        destination: _DestinationWriter,
        limit: int = 10_000,
        cancellation_requested: Callable[[], bool] | None = None,
        execution_ref: str | None = None,
        now: str | None = None,
    ) -> dict[str, object]:
        """Read, durably write the destination, then advance the checkpoint."""

        def ensure_not_cancelled() -> None:
            if cancellation_requested is not None and cancellation_requested():
                raise IngestionSyncCancelled("connector sync cancellation was requested")

        ensure_not_cancelled()
        scoped_identity = scoped_checkpoint_identity(workspace_id, definition.checkpoint_identity)
        health = self._checkpoints.health(scoped_identity)
        expected = self._checkpoints.get(scoped_identity)
        plan = self._registry.plan_sync(definition, checkpoint_present=health.present)
        fence = self._checkpoints.acquire(scoped_identity)
        result = self._registry.read(
            definition.connector_id,
            connection,
            asset,
            secrets,
            limit=limit,
            checkpoint=expected,
        )
        ensure_not_cancelled()
        if result.checkpoint is None:
            raise ValueError("connector sync execution must return a next checkpoint")
        with self._writer_lease():
            ensure_not_cancelled()
            output_id, output_digest = destination.write(
                definition.destination_ref,
                result,
                fence=fence,
            )
            # If cancellation arrives during the output write, leave the content-addressed
            # object unreferenced for retention and do not advance the source checkpoint.
            ensure_not_cancelled()
            catalog_commit = None
            lineage: LineageEdge | None = None
            if (
                definition.source_revision_ref is not None
                and definition.destination_asset_id is not None
            ):
                if not execution_ref or not execution_ref.strip() or now is None:
                    raise ValueError("governed sync requires a durable execution_ref and timestamp")
                if len(output_digest) != 64 or any(
                    character not in "0123456789abcdef" for character in output_digest
                ):
                    raise ValueError("governed sync output digest must be lowercase SHA-256 hex")
                target_ref = AssetRef(
                    definition.destination_asset_id,
                    AssetVersion(f"sha256:{output_digest}"),
                )
                schema_bytes = encode(
                    [
                        {
                            "name": field.name,
                            "data_type": field.data_type,
                            "nullable": field.nullable,
                        }
                        for field in result.fields
                    ]
                )
                revision = AssetRevision(
                    target_ref,
                    schema_digest=hashlib.sha256(schema_bytes).hexdigest(),
                    content_digest=output_digest,
                    metadata=(("sync_id", definition.id),),
                )
                lineage = LineageEdge(
                    definition.source_revision_ref,
                    target_ref,
                    operation="write",
                    mode="observed",
                    execution_ref=execution_ref,
                )
                catalog_commit = (
                    WorkspaceId(workspace_id),
                    revision,
                    lineage,
                    now,
                    (
                        definition.connector_id,
                        definition.connection_ref,
                        (
                            definition.asset_ref.split("::", 1)[1]
                            if definition.asset_ref.startswith(f"{definition.connection_ref}::")
                            else definition.asset_ref
                        ),
                    ),
                )
            evidence = self._checkpoints.commit_output_then_checkpoint(
                scoped_identity,
                expected,
                result.checkpoint,
                output_id=output_id,
                output_digest=output_digest,
                fence=fence,
                output_committed=True,
                catalog_commit=catalog_commit,
            )
        checkpoint_payload = evidence.to_payload()
        if isinstance(checkpoint_payload, dict) and "identity" in checkpoint_payload:
            checkpoint_payload["identity"] = definition.checkpoint_identity
        response: dict[str, object] = {
            "schema": "ronin.ingestion-sync-result/v1",
            "plan": plan.to_payload(),
            "rows_written": len(result.rows),
            "checkpoint": checkpoint_payload,
        }
        if lineage is not None:
            response["lineage"] = lineage.to_payload()
        return response


__all__ = (
    "ArtifactDestinationWriter",
    "IngestionSyncDefinition",
    "IngestionSyncPlan",
    "IngestionSyncService",
    "plan_sync",
    "scoped_checkpoint_identity",
)
