"""Bounded telemetry, redaction and audit records for AI Studio."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any

_SECRET_TERMS = ("authorization", "cookie", "password", "secret", "token", "api_key", "credential")


def redact_mapping(values: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow redacted copy; nested payloads are never logged by default."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        folded = key.casefold()
        result[key] = "[REDACTED]" if any(term in folded for term in _SECRET_TERMS) else value
    return result


def workspace_label(workspace_id: str) -> str:
    if not workspace_id or len(workspace_id) > 256:
        raise ValueError("invalid workspace id")
    return hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class AuditRecord:
    action: str
    resource: str
    outcome: str
    request_id: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.action
            or not self.resource
            or self.outcome not in {"success", "denied", "failure"}
        ):
            raise ValueError("invalid audit record")
        if any(any(term in key.casefold() for term in _SECRET_TERMS) for key, _ in self.metadata):
            raise ValueError("audit metadata cannot contain secret keys")


class Metrics:
    """Small bounded counter set; labels are controlled by the caller."""

    def __init__(self, *, max_series: int = 10_000) -> None:
        if max_series < 1:
            raise ValueError("max_series must be positive")
        self._max_series = max_series
        self._counters: Counter[tuple[str, ...]] = Counter()

    def increment(self, name: str, *labels: str) -> None:
        if not name or any(not label or len(label) > 128 for label in (name, *labels)):
            raise ValueError("metric names and labels must be bounded")
        key = (name, *labels)
        if key not in self._counters and len(self._counters) >= self._max_series:
            raise ValueError("metric cardinality limit exceeded")
        self._counters[key] += 1

    def snapshot(self) -> dict[tuple[str, ...], int]:
        return dict(self._counters)
