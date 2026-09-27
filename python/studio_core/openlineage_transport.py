"""Provider-neutral, bounded OpenLineage transport contract."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .canonical_json import encode as encode_canonical_json
from .openlineage import JsonValue

OPENLINEAGE_API_VERSION = "1.0"
SUPPORTED_OPENLINEAGE_SCHEMA_VERSIONS = frozenset({OPENLINEAGE_API_VERSION})


class OpenLineageTransportError(RuntimeError):
    """Raised when an event cannot be delivered after bounded retries."""


class OpenLineageSink(Protocol):
    def publish(self, event: Mapping[str, JsonValue]) -> None: ...


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    event_digest: str
    attempts: int
    deduplicated: bool


def validate_openlineage_event(event: Mapping[str, JsonValue]) -> None:
    """Validate the bounded, supported OpenLineage event subset."""
    required = {"eventType", "eventTime", "run", "job", "producer"}
    if not required <= set(event):
        raise ValueError("OpenLineage event is missing required fields")
    if event.get("producer") != "ronin":
        raise ValueError("OpenLineage producer is unsupported")
    schema_version = event.get("schemaVersion", OPENLINEAGE_API_VERSION)
    if schema_version not in SUPPORTED_OPENLINEAGE_SCHEMA_VERSIONS:
        raise ValueError("OpenLineage schemaVersion is unsupported")
    event_type = event.get("eventType")
    if event_type not in {"START", "RUNNING", "COMPLETE", "ABORT", "FAIL", "OTHER"}:
        raise ValueError("OpenLineage event type is unsupported")
    event_time = event.get("eventTime")
    if not isinstance(event_time, str) or not event_time.endswith("Z"):
        raise ValueError("OpenLineage eventTime must be a UTC timestamp")
    run = event.get("run")
    job = event.get("job")
    if not isinstance(run, Mapping) or not isinstance(job, Mapping):
        raise ValueError("OpenLineage run and job must be objects")
    run_id = run.get("runId")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("OpenLineage run.runId is required")
    namespace = job.get("namespace")
    name = job.get("name")
    if (
        not isinstance(namespace, str)
        or not namespace.strip()
        or not isinstance(name, str)
        or not name.strip()
    ):
        raise ValueError("OpenLineage job namespace and name are required")


class OpenLineageTransport:
    """Retrying, idempotent transport wrapper around a provider sink."""

    def __init__(self, sink: OpenLineageSink, *, max_attempts: int = 3) -> None:
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        self._sink = sink
        self._max_attempts = max_attempts
        self._published: set[str] = set()

    @staticmethod
    def _digest(event: Mapping[str, JsonValue]) -> str:
        return hashlib.sha256(encode_canonical_json(dict(event))).hexdigest()

    def publish(self, event: Mapping[str, JsonValue]) -> PublishReceipt:
        validate_openlineage_event(event)
        digest = self._digest(event)
        if digest in self._published:
            return PublishReceipt(digest, 0, True)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                self._sink.publish(event)
            except Exception as exc:  # noqa: BLE001 - sink failures are retryable transport errors
                last_error = exc
                continue
            self._published.add(digest)
            return PublishReceipt(digest, attempt, False)
        raise OpenLineageTransportError(
            f"OpenLineage publish failed after {self._max_attempts} attempts"
        ) from last_error


__all__ = [
    "OPENLINEAGE_API_VERSION",
    "SUPPORTED_OPENLINEAGE_SCHEMA_VERSIONS",
    "OpenLineageSink",
    "OpenLineageTransport",
    "OpenLineageTransportError",
    "PublishReceipt",
    "validate_openlineage_event",
]
