"""Data Engineering lineage boundary backed by Ronin's catalog contracts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast

from studio_core import AssetRef, LineageEdge, LineageOperation, WorkspaceId, lineage_event_payload
from studio_orchestrator import Instant


class LineageCatalog(Protocol):
    def put_lineage(
        self, workspace_id: WorkspaceId, edge: LineageEdge, *, now: Instant | str
    ) -> LineageEdge: ...


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


__all__ = ("LineageCatalog", "publish_lineage_event", "record_pipeline_lineage")
