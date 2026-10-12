from __future__ import annotations

import pytest
from studio_core import catalog, plugin_events, transport_policy


@pytest.mark.parametrize("value", [123, " value", "value\x00tail", "value\nnext"])
def test_catalog_text_boundary_rejects_noncanonical_values(value: object) -> None:
    with pytest.raises(ValueError, match="catalog field"):
        catalog._require_text(value, "catalog field")  # type: ignore[arg-type]


def _event(**overrides: object) -> plugin_events.PluginEvent:
    values: dict[str, object] = {
        "event_id": "event-1",
        "event_type": "sample.v1",
        "producer": "producer",
        "tenant_id": "tenant",
        "correlation_id": "correlation",
        "occurred_at": "2026-10-12T00:00:00Z",
        "payload": {"value": 1},
    }
    values.update(overrides)
    return plugin_events.new_event(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field", ["event_id", "event_type", "producer", "tenant_id", "correlation_id"]
)
def test_plugin_event_identity_rejects_noncanonical_values(field: str) -> None:
    with pytest.raises(plugin_events.PluginEventError, match="identity fields"):
        _event(**{field: 123})
    with pytest.raises(plugin_events.PluginEventError, match="identity fields"):
        _event(**{field: "value\x00tail"})


def test_plugin_event_outbox_is_idempotent_and_conflicts_fail_closed() -> None:
    event = _event()
    outbox = plugin_events.InMemoryOutbox(max_events=1)
    first = outbox.append(event)
    assert outbox.append(event) is first
    with pytest.raises(plugin_events.PluginEventError, match="conflict"):
        outbox.append(_event(payload={"value": 2}))
    assert outbox.pending() == (first,)
    outbox.mark_published(event.event_id)
    assert outbox.pending() == ()


def test_plugin_event_inbox_runs_handler_once_and_enforces_capacity() -> None:
    event = _event()
    inbox = plugin_events.InMemoryInbox(max_events=1)
    seen: list[str] = []
    assert inbox.process_once("consumer", event, lambda value: seen.append(value.event_id))
    assert not inbox.process_once("consumer", event, lambda value: seen.append(value.event_id))
    assert seen == [event.event_id]
    with pytest.raises(plugin_events.PluginEventError, match="capacity"):
        inbox.process_once("other", _event(event_id="event-2"), lambda _value: None)
    with pytest.raises(plugin_events.PluginEventError, match="consumer_id"):
        inbox.process_once(123, event, lambda _value: None)  # type: ignore[arg-type]


def test_transport_policy_closed_vocabulary_and_plaintext_decision_are_distinct() -> None:
    assert transport_policy.parse_bind_policy(None) == "loopback"
    assert not transport_policy.allows_plaintext_non_loopback("loopback")
    assert transport_policy.allows_plaintext_non_loopback("container-internal")
    assert transport_policy.allows_plaintext_non_loopback("insecure-plaintext-network")
    with pytest.raises(ValueError, match="must be one of"):
        transport_policy.parse_bind_policy("invalid")  # type: ignore[arg-type]
