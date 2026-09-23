"""Runtime-neutral execution backend contract.

The control plane submits a bounded WorkloadSpec to this port. Docker,
Kubernetes and VM adapters must preserve these semantics and the worker/v1
protocol; they must not leak runtime-specific objects into domain code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class WorkloadState(StrEnum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    cpu: str = "1"
    memory: str = "512Mi"
    ephemeral_storage: str = "1Gi"

    def __post_init__(self) -> None:
        for name in ("cpu", "memory", "ephemeral_storage"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a trimmed non-empty quantity")


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    run_id: str
    worker_protocol: str
    image: str
    command: tuple[str, ...] = ()
    environment_refs: tuple[str, ...] = ()
    input_artifacts: tuple[str, ...] = ()
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    timeout_seconds: int = 900
    network_policy: str = "local-only"
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("run_id", "worker_protocol", "image", "network_policy"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be a trimmed non-empty string")
        if (
            not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")
        if not self.command:
            raise ValueError("command must not be empty")
        if any(not item or item != item.strip() for item in self.command):
            raise ValueError("command entries must be trimmed and non-empty")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not key.strip()
            or not value.strip()
            for key, value in self.labels.items()
        ):
            raise ValueError("labels must contain non-empty keys and values")


@dataclass(frozen=True, slots=True)
class WorkloadHandle:
    workload_id: str
    run_id: str
    backend: str


@dataclass(frozen=True, slots=True)
class WorkloadStatus:
    handle: WorkloadHandle
    state: WorkloadState
    reason: str | None = None
    observed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    backend: str
    supports_logs: bool = True
    supports_cancellation: bool = True
    supports_reconciliation: bool = True
    runtime_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class LogBatch:
    lines: tuple[str, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    handle: WorkloadHandle
    state: WorkloadState
    runtime_fingerprint: str | None
    artifact_refs: tuple[str, ...] = ()


class ExecutionBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...
    def submit(self, spec: WorkloadSpec) -> WorkloadHandle: ...
    def get_status(self, handle: WorkloadHandle) -> WorkloadStatus: ...
    def stream_logs(self, handle: WorkloadHandle, cursor: str | None = None) -> LogBatch: ...
    def cancel(self, handle: WorkloadHandle, reason: str) -> None: ...
    def delete(self, handle: WorkloadHandle) -> None: ...
    def collect_evidence(self, handle: WorkloadHandle) -> ExecutionEvidence: ...


class InMemoryExecutionBackend:
    """Deterministic conformance backend; it never represents real isolation."""

    def __init__(self, *, fingerprint: str = "in-memory/test") -> None:
        self._fingerprint = fingerprint
        self._records: dict[str, tuple[WorkloadSpec, WorkloadStatus, tuple[str, ...]]] = {}

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities("in-memory", runtime_fingerprint=self._fingerprint)

    def submit(self, spec: WorkloadSpec) -> WorkloadHandle:
        existing = next(
            (
                record[1].handle
                for record in self._records.values()
                if record[0].run_id == spec.run_id
            ),
            None,
        )
        if existing is not None:
            return existing
        handle = WorkloadHandle(f"memory-{len(self._records) + 1}", spec.run_id, "in-memory")
        status = WorkloadStatus(handle, WorkloadState.SUBMITTED)
        self._records[handle.workload_id] = (spec, status, ())
        return handle

    def get_status(self, handle: WorkloadHandle) -> WorkloadStatus:
        return self._record(handle)[1]

    def stream_logs(self, handle: WorkloadHandle, cursor: str | None = None) -> LogBatch:
        lines = self._record(handle)[2]
        start = int(cursor or "0")
        return LogBatch(lines[start:], str(len(lines)))

    def cancel(self, handle: WorkloadHandle, reason: str) -> None:
        spec, status, logs = self._record(handle)
        if status.state in {WorkloadState.SUCCEEDED, WorkloadState.FAILED, WorkloadState.CANCELLED}:
            return
        self._records[handle.workload_id] = (
            spec,
            WorkloadStatus(handle, WorkloadState.CANCELLED, reason),
            logs,
        )

    def delete(self, handle: WorkloadHandle) -> None:
        self._records.pop(handle.workload_id, None)

    def collect_evidence(self, handle: WorkloadHandle) -> ExecutionEvidence:
        status = self.get_status(handle)
        return ExecutionEvidence(handle, status.state, self._fingerprint)

    def _record(
        self, handle: WorkloadHandle
    ) -> tuple[WorkloadSpec, WorkloadStatus, tuple[str, ...]]:
        if handle.backend != "in-memory" or handle.workload_id not in self._records:
            raise KeyError(f"unknown workload: {handle.workload_id}")
        return self._records[handle.workload_id]


__all__ = (
    "BackendCapabilities",
    "ExecutionBackend",
    "ExecutionEvidence",
    "InMemoryExecutionBackend",
    "LogBatch",
    "ResourceLimits",
    "WorkloadHandle",
    "WorkloadSpec",
    "WorkloadState",
    "WorkloadStatus",
)
