"""Provider-neutral notification intents for alert and FinOps transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from studio_orchestrator import Instant

from .alerts import AlertTransition


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    id: str
    kind: str
    title: str
    body: str
    created_at: Instant
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for value, name in ((self.id, "notification id"), (self.kind, "notification kind"), (self.title, "notification title")):
            if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
                raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
        if not self.body or "\x00" in self.body:
            raise ValueError("notification body must be non-empty")
        object.__setattr__(self, "created_at", Instant(self.created_at))
        attributes = tuple(sorted(self.attributes))
        keys = [key for key, _ in attributes]
        if len(keys) != len(set(keys)):
            raise ValueError("notification attribute keys must be unique")
        object.__setattr__(self, "attributes", attributes)


@runtime_checkable
class NotificationSink(Protocol):
    def send(self, intent: NotificationIntent) -> str: ...


def alert_notification(
    transition: AlertTransition,
    *,
    now: Instant | str,
) -> NotificationIntent | None:
    """Map an alert state transition to one notification intent without sending it."""

    if not transition.changed or transition.current is None:
        return None
    state = transition.current.status
    value = transition.current.value
    intent_id = (
        f"alert:{transition.rule.id}:{transition.current.fingerprint}:"
        f"{state}:{transition.current.updated_at}"
    )
    return NotificationIntent(
        intent_id,
        "alert",
        f"{transition.rule.name}: {state}",
        (
            f"Metric {transition.rule.metric_name} is {value}; "
            f"rule {transition.rule.operator} {transition.rule.threshold}."
        ),
        Instant(now),
        (
            ("rule_id", transition.rule.id),
            ("status", state),
            ("metric_name", transition.rule.metric_name),
        ),
    )


__all__ = ("NotificationIntent", "NotificationSink", "alert_notification")
