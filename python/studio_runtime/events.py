"""Runtime dispatcher for versioned plugin events."""

from __future__ import annotations

from dataclasses import dataclass

from studio_core.plugin_events import (
    InMemoryInbox,
    InMemoryOutbox,
    PluginEvent,
    PluginEventSchemaRegistry,
)
from studio_core.plugins import EventSubscriptionRegistry


@dataclass(frozen=True, slots=True)
class DispatchResult:
    event_id: str
    delivered: tuple[str, ...]
    failed: tuple[str, ...]


class PluginEventDispatcher:
    """Dispatches outbox records without allowing one plugin to stop others."""

    def __init__(
        self,
        subscriptions: EventSubscriptionRegistry,
        *,
        outbox: InMemoryOutbox | None = None,
        inbox: InMemoryInbox | None = None,
        schemas: PluginEventSchemaRegistry | None = None,
    ) -> None:
        self.subscriptions = subscriptions
        self.outbox = outbox or InMemoryOutbox()
        self.inbox = inbox or InMemoryInbox()
        self.schemas = schemas

    def publish(self, event: PluginEvent) -> None:
        if self.schemas is not None:
            self.schemas.validate(event)
        self.outbox.append(event)

    def dispatch_pending(self, *, limit: int = 100) -> tuple[DispatchResult, ...]:
        results: list[DispatchResult] = []
        for record in self.outbox.pending(limit=limit):
            if self.schemas is not None:
                self.schemas.validate(record.event)
            delivered: list[str] = []
            failed: list[str] = []
            matching = (
                item
                for item in self.subscriptions.items
                if item.event_type == record.event.event_type
            )
            for subscription in matching:
                consumer_id = f"{subscription.plugin_id}:{subscription.event_type}"
                try:
                    processed = self.inbox.process_once(
                        consumer_id,
                        record.event,
                        subscription.handler,
                    )
                except Exception:
                    failed.append(subscription.plugin_id)
                else:
                    if processed:
                        delivered.append(subscription.plugin_id)
            if not failed:
                self.outbox.mark_published(record.event.event_id)
            results.append(
                DispatchResult(record.event.event_id, tuple(delivered), tuple(sorted(set(failed))))
            )
        return tuple(results)


__all__ = ("DispatchResult", "PluginEventDispatcher")
