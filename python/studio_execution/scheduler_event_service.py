"""Bounded application service for durable scheduler event deliveries."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from studio_orchestrator import Instant
from studio_storage.scheduler_events import (
    EventDelivery,
    SchedulerEventRecord,
    SchedulerEventStore,
    WorkspaceId,
)


@dataclass(frozen=True, slots=True)
class EventDeliveryResult:
    delivered: tuple[EventDelivery, ...]


class SchedulerEventService:
    """Ingest events and convert frozen pending deliveries into WorkflowRuns."""

    def __init__(self, store: SchedulerEventStore) -> None:
        self._store = store

    async def ingest(self, event: SchedulerEventRecord) -> tuple[EventDelivery, ...]:
        return await asyncio.to_thread(self._store.ingest_event, event)

    async def process_pending(
        self,
        workspace_id: WorkspaceId,
        *,
        now: Instant | str,
        limit: int = 100,
    ) -> EventDeliveryResult:
        pending = await asyncio.to_thread(
            self._store.list_pending_deliveries,
            workspace_id,
            limit=limit,
        )
        delivered: list[EventDelivery] = []
        for delivery in pending:
            delivered.append(
                await asyncio.to_thread(
                    self._store.deliver_event,
                    delivery,
                    now=now,
                )
            )
        return EventDeliveryResult(tuple(delivered))


__all__ = ("EventDeliveryResult", "SchedulerEventService")
