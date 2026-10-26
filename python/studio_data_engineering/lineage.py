"""Data Engineering lineage boundary backed by Ronin's catalog contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast

from studio_core import (
    AssetRef,
    LineageEdge,
    LineageOperation,
    WorkspaceId,
    lineage_event_payload,
    validate_openlineage_event,
)
from studio_orchestrator import Instant

_RUN_EVENT_TYPE = "openlineage.run-event.v1"
_DATASET_EVENT_TYPE = "openlineage.dataset-event.v1"


class LineageCatalog(Protocol):
    def put_lineage(
        self, workspace_id: WorkspaceId, edge: LineageEdge, *, now: Instant | str
    ) -> LineageEdge: ...


class LineageOutbox(Protocol):
    def enqueue(
        self,
        *,
        event_id: str,
        event_type: str,
        aggregate_key: str,
        payload: Mapping[str, object],
    ) -> bool: ...

    def pending_events(
        self, *, limit: int = 100, event_type: str | tuple[str, ...] | None = None
    ) -> tuple[dict[str, object], ...]: ...

    def mark_published(self, event_id: str) -> bool: ...


def record_pipeline_lineage(
    catalog: LineageCatalog,
    *,
    workspace_id: str,
    source: AssetRef,
    target: AssetRef,
    operation: str,
    execution_ref: str,
    now: Instant | str,
) -> LineageEdge:
    """Commit one observed pipeline edge through the governed catalog."""
    if not execution_ref.strip():
        raise ValueError("execution_ref must be non-empty")
    edge = LineageEdge(
        source=source,
        target=target,
        operation=cast(LineageOperation, operation),
        mode="observed",
        execution_ref=execution_ref,
    )
    return catalog.put_lineage(WorkspaceId(workspace_id), edge, now=now)


async def publish_lineage_event(
    edge: LineageEdge,
    publish: Callable[[Mapping[str, object]], Awaitable[None]],
    *,
    namespace: str,
    event_time: str,
    job_name: str | None = None,
) -> None:
    """Publish a deterministic OpenLineage-compatible event after persistence."""
    await publish(
        lineage_event_payload(
            edge,
            namespace=namespace,
            event_time=event_time,
            job_name=job_name,
        )
    )


def enqueue_lineage_event(
    outbox: LineageOutbox,
    edge: LineageEdge,
    *,
    namespace: str,
    event_time: str,
    job_name: str | None = None,
) -> str:
    """Persist a validated OpenLineage event with a replay-stable outbox ID."""
    event = lineage_event_payload(
        edge,
        namespace=namespace,
        event_time=event_time,
        job_name=job_name,
    )
    validate_openlineage_event(event)
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), allow_nan=False)
    event_id = f"openlineage-{hashlib.sha256(canonical.encode()).hexdigest()}"
    event_type = _DATASET_EVENT_TYPE if "dataset" in event else _RUN_EVENT_TYPE
    aggregate_key = (
        f"{edge.source.asset_id}@{edge.source.version}->"
        f"{edge.target.asset_id}@{edge.target.version}"
    )
    outbox.enqueue(
        event_id=event_id,
        event_type=event_type,
        aggregate_key=aggregate_key,
        payload=event,
    )
    return event_id


def record_pipeline_lineage_and_enqueue(
    catalog: LineageCatalog,
    outbox: LineageOutbox,
    *,
    workspace_id: str,
    source: AssetRef,
    target: AssetRef,
    operation: str,
    execution_ref: str,
    now: Instant | str,
    namespace: str,
    event_time: str,
    job_name: str | None = None,
) -> tuple[LineageEdge, str]:
    """Persist governed lineage, then durably enqueue its OpenLineage export.

    If the process stops between the two writes, replaying these exact arguments
    is safe: catalog lineage identities and outbox IDs are deterministic.
    """
    edge = record_pipeline_lineage(
        catalog,
        workspace_id=workspace_id,
        source=source,
        target=target,
        operation=operation,
        execution_ref=execution_ref,
        now=now,
    )
    event_id = enqueue_lineage_event(
        outbox,
        edge,
        namespace=namespace,
        event_time=event_time,
        job_name=job_name,
    )
    return edge, event_id


async def publish_pending_lineage_events(
    outbox: LineageOutbox,
    publish: Callable[[Mapping[str, object]], Awaitable[None]],
    *,
    limit: int = 100,
) -> tuple[str, ...]:
    """Deliver bounded lineage events and acknowledge only after success.

    Delivery is at-least-once: a crash after remote success but before the local
    acknowledgement can replay the same deterministic event ID and payload.
    """
    published: list[str] = []
    for record in outbox.pending_events(
        limit=limit,
        event_type=(_RUN_EVENT_TYPE, _DATASET_EVENT_TYPE),
    ):
        event_id = record.get("event_id")
        payload = record.get("payload")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("OpenLineage outbox record is missing its event ID")
        if not isinstance(payload, Mapping):
            raise ValueError("OpenLineage outbox record payload must be an object")
        validate_openlineage_event(payload)
        await publish(payload)
        if outbox.mark_published(event_id):
            published.append(event_id)
    return tuple(published)


__all__ = (
    "LineageCatalog",
    "LineageOutbox",
    "enqueue_lineage_event",
    "publish_lineage_event",
    "publish_pending_lineage_events",
    "record_pipeline_lineage",
    "record_pipeline_lineage_and_enqueue",
)
