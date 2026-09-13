"""Bounded application service for durable scheduler event deliveries."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from studio_orchestrator import Instant
from studio_storage.scheduler_events import (
    EventDelivery,
    SchedulerEventRecord,
    SchedulerEventStore,
    WorkspaceId,
)

AuthorityCheck = Callable[[Instant | str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class EventDeliveryResult:
    delivered: tuple[EventDelivery, ...]


class SchedulerEventService:
    """Ingest events and convert frozen pending deliveries into WorkflowRuns."""

    def __init__(
        self,
        store: SchedulerEventStore,
        *,
        authority_check: AuthorityCheck | None = None,
    ) -> None:
        self._store = store
        self._authority_check = authority_check

    async def _check_authority(self, now: Instant | str) -> None:
        if self._authority_check is not None:
            await self._authority_check(now)

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
            await self._check_authority(now)
            delivered.append(
                await asyncio.to_thread(
                    self._store.deliver_event,
                    delivery,
                    now=now,
                )
            )
        return EventDeliveryResult(tuple(delivered))


__all__ = ("AuthorityCheck", "EventDeliveryResult", "SchedulerEventService")
