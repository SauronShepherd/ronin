"""Provider-neutral durable event-trigger definitions for scheduler workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .scheduler import WorkflowId


def _require_text(value: str, name: str, *, maximum: int = 512) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters")
    return value


@dataclass(frozen=True, order=True, slots=True)
class EventTriggerId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "event trigger id", maximum=256)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class SchedulerEventId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "scheduler event id", maximum=256)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class EventTriggerDefinition:
    """Exact-match event routing rule; payload interpretation stays outside core."""

    id: EventTriggerId
    workflow_id: WorkflowId
    event_type: str
    source_ref: str | None = None
    subject_ref: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        _require_text(self.event_type, "event type")
        if self.source_ref is not None:
            _require_text(self.source_ref, "event trigger source_ref")
        if self.subject_ref is not None:
            _require_text(self.subject_ref, "event trigger subject_ref")

    def matches(
        self,
        *,
        event_type: str,
        source_ref: str | None,
        subject_ref: str | None,
    ) -> bool:
        if not self.enabled or self.event_type != event_type:
            return False
        if self.source_ref is not None and self.source_ref != source_ref:
            return False
        return self.subject_ref is None or self.subject_ref == subject_ref

    def to_payload(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "event_type": self.event_type,
            "source_ref": self.source_ref,
            "subject_ref": self.subject_ref,
            "enabled": self.enabled,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> EventTriggerDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "workflow_id",
            "event_type",
            "source_ref",
            "subject_ref",
            "enabled",
        }:
            raise ValueError("event trigger definition has invalid shape")
        identifier = payload["id"]
        workflow_id = payload["workflow_id"]
        event_type = payload["event_type"]
        source_ref = payload["source_ref"]
        subject_ref = payload["subject_ref"]
        enabled = payload["enabled"]
        if not isinstance(identifier, str) or not isinstance(workflow_id, str):
            raise ValueError("event trigger ids must be strings")
        if not isinstance(event_type, str) or not isinstance(enabled, bool):
            raise ValueError("event trigger type/enabled fields have invalid types")
        if source_ref is not None and not isinstance(source_ref, str):
            raise ValueError("event trigger source_ref must be string or null")
        if subject_ref is not None and not isinstance(subject_ref, str):
            raise ValueError("event trigger subject_ref must be string or null")
        return cls(
            EventTriggerId(identifier),
            WorkflowId(workflow_id),
            event_type,
            source_ref,
            subject_ref,
            enabled,
        )

    @classmethod
    def from_json(cls, payload: str) -> EventTriggerDefinition:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = (
    "EventTriggerDefinition",
    "EventTriggerId",
    "SchedulerEventId",
)
