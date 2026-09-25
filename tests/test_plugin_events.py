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


def test_outbox_rejects_invalid_limits_and_unknown_publication() -> None:
    with pytest.raises(ValueError, match="max_events"):
        InMemoryOutbox(max_events=0)
    outbox = InMemoryOutbox()
    with pytest.raises(ValueError, match="between 1 and 1000"):
        outbox.pending(limit=0)
    with pytest.raises(ValueError, match="between 1 and 1000"):
        outbox.pending(limit=1001)
    with pytest.raises(KeyError):
        outbox.mark_published("missing")


def test_inbox_applies_duplicate_event_only_once() -> None:
    inbox = InMemoryInbox()
    seen: list[str] = []

    event = _event()
    assert inbox.process_once("consumer", event, lambda item: seen.append(item.event_id))
    assert not inbox.process_once("consumer", event, lambda item: seen.append(item.event_id))
    assert seen == ["event-1"]


def test_inbox_retries_after_handler_failure() -> None:
    inbox = InMemoryInbox()
    attempts = 0

    def handler(_event) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient")

    with pytest.raises(RuntimeError, match="transient"):
        inbox.process_once("consumer", _event(), handler)

    assert inbox.process_once("consumer", _event(), handler)
    assert attempts == 2


def test_inbox_rejects_invalid_capacity_and_enforces_limit() -> None:
    with pytest.raises(ValueError, match="max_events"):
        InMemoryInbox(max_events=0)

    inbox = InMemoryInbox(max_events=1)
    assert inbox.process_once("consumer", _event(), lambda _event: None)
    second = replace(_event(), event_id="event-2")
    with pytest.raises(PluginEventError, match="capacity"):
        inbox.process_once("consumer", second, lambda _event: None)


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


def test_event_schema_registry_rejects_invalid_duplicates_and_sorts_items() -> None:
    schemas = PluginEventSchemaRegistry()
    with pytest.raises(PluginEventError, match="duplicate"):
        schemas.register(PluginEventSchema("projects.created.v1", 1, ("id", "id")))
    schemas.register(PluginEventSchema("z.last.v1", 1))
    schemas.register(PluginEventSchema("a.first.v1", 1))
    with pytest.raises(PluginEventError, match="collision"):
        schemas.register(PluginEventSchema("a.first.v1", 1))
    assert tuple(schema.event_type for schema in schemas.items) == (
        "a.first.v1",
        "z.last.v1",
    )
