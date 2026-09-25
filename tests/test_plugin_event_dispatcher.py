from __future__ import annotations

import pytest

from studio_core.plugin_events import (
    PluginEventError,
    PluginEventSchema,
    PluginEventSchemaRegistry,
    new_event,
)
from studio_core.plugins import EventSubscriptionRegistry
from studio_runtime import PluginEventDispatcher


def _event():
    return new_event(
        event_id="event-1",
        event_type="projects.created.v1",
        producer="projects",
        tenant_id="tenant-1",
        correlation_id="correlation-1",
        occurred_at="2026-01-01T00:00:00Z",
        payload={"project_id": "project-1"},
    )


def test_dispatcher_delivers_to_matching_subscribers_and_marks_published() -> None:
    registry = EventSubscriptionRegistry()
    seen: list[str] = []
    registry.add("projects.created.v1", "consumer", lambda event: seen.append(event.event_id))
    registry.freeze()
    dispatcher = PluginEventDispatcher(registry)
    dispatcher.publish(_event())

    result = dispatcher.dispatch_pending()

    assert result[0].delivered == ("consumer",)
    assert result[0].failed == ()
    assert seen == ["event-1"]
    assert dispatcher.outbox.pending() == ()


def test_dispatcher_isolates_failure_and_retries_failed_event() -> None:
    registry = EventSubscriptionRegistry()
    calls: list[str] = []

    def failing(_event) -> None:
        calls.append("failed")
        raise RuntimeError("consumer unavailable")

    registry.add("projects.created.v1", "bad", failing)
    registry.freeze()
    dispatcher = PluginEventDispatcher(registry)
    dispatcher.publish(_event())

    first = dispatcher.dispatch_pending()[0]
    second = dispatcher.dispatch_pending()[0]

    assert first.failed == ("bad",)
    assert second.failed == ("bad",)
    assert calls == ["failed", "failed"]
    assert dispatcher.outbox.pending()[0].event.event_id == "event-1"


def test_dispatcher_rejects_unknown_event_schema_before_outbox() -> None:
    registry = EventSubscriptionRegistry()
    registry.freeze()
    schemas = PluginEventSchemaRegistry()
    schemas.register(PluginEventSchema("other.event.v1", 1))
    dispatcher = PluginEventDispatcher(registry, schemas=schemas)

    with pytest.raises(PluginEventError, match="unknown event schema"):
        dispatcher.publish(_event())
