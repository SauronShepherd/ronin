from __future__ import annotations

from dataclasses import replace

import pytest

from studio_core.plugin_events import (
    InMemoryInbox,
    InMemoryOutbox,
    PluginEventError,
    PluginEventSchema,
    PluginEventSchemaRegistry,
    new_event,
)


def _event(payload: dict[str, object] | None = None):
    return new_event(
        event_id="event-1",
        event_type="projects.created.v1",
        producer="example",
        tenant_id="tenant-1",
        correlation_id="correlation-1",
        occurred_at="2026-01-01T00:00:00Z",
        payload=payload or {"project_id": "project-1"},
    )


def test_outbox_append_is_idempotent_and_conflicts_fail_closed() -> None:
    outbox = InMemoryOutbox(max_events=2)
    first = outbox.append(_event())

    assert outbox.append(first.event) == first
    with pytest.raises(PluginEventError, match="conflict"):
        outbox.append(_event({"project_id": "different"}))
    assert outbox.pending()[0].event.event_id == "event-1"
    outbox.mark_published("event-1")
    assert outbox.pending() == ()


def test_inbox_applies_duplicate_event_only_once() -> None:
    inbox = InMemoryInbox()
    seen: list[str] = []

    event = _event()
    assert inbox.process_once("consumer", event, lambda item: seen.append(item.event_id))
    assert not inbox.process_once("consumer", event, lambda item: seen.append(item.event_id))
    assert seen == ["event-1"]


def test_event_requires_versioned_type_and_valid_identity() -> None:
    event = _event()
    invalid = replace(event, event_type="projects.created")

    with pytest.raises(PluginEventError, match="schema version"):
        invalid.validate()


def test_event_schema_registry_validates_payload_contract() -> None:
    schemas = PluginEventSchemaRegistry()
    schemas.register(PluginEventSchema("projects.created.v1", 1, ("project_id",)))
    schemas.validate(_event())

    with pytest.raises(PluginEventError, match="missing fields"):
        schemas.validate(_event({"name": "missing-id"}))
