"""Storage-neutral durable execution port."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from studio_kernel import ExecutionEvidenceReference
from studio_orchestrator.instants import Instant
from studio_orchestrator.lifecycle import (
    AttemptId,
    AttemptState,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
)


@dataclass(frozen=True, slots=True)
class Page:
    items: tuple[Job, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimedRun:
    job: Job
    run: Run
    attempt_id: AttemptId
    attempt_ordinal: int
    lease_token: LeaseToken


@dataclass(frozen=True, slots=True)
class StoredExecutionEvent:
    attempt_id: AttemptId
    sequence: int
    kind: str
    message: str
    occurred_at: Instant

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", Instant(self.occurred_at))


@dataclass(frozen=True, slots=True)
class RunExecutionEvent:
    """Run-global projection of one attempt-local durable event."""

    sequence: int
    attempt_id: AttemptId
    attempt_sequence: int
    kind: str
    message: str
    occurred_at: Instant

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("run event sequence must be non-negative")
        if self.attempt_sequence < 0:
            raise ValueError("attempt event sequence must be non-negative")
        object.__setattr__(self, "occurred_at", Instant(self.occurred_at))


@dataclass(frozen=True, slots=True)
class EventPage:
    """Bounded Run-global event page with an opaque polling cursor."""

    items: tuple[RunExecutionEvent, ...]
    next_since: str


@dataclass(frozen=True, slots=True)
class StoredCellResult:
    run_id: RunId
    cell_id: str
    source_digest: str
    execution_identity_digest: str
    state: str
    result_json: str
    updated_at: Instant

    def __post_init__(self) -> None:
        object.__setattr__(self, "updated_at", Instant(self.updated_at))


@dataclass(frozen=True, slots=True)
class StoredEvidenceRef:
    """Run/cell ownership wrapped around one portable evidence reference."""

    run_id: RunId
    cell_id: str | None
    role: str
    digest_algorithm: str
    digest: str
    media_type: str | None
    size_bytes: int | None
    storage_ref: str | None

    def __post_init__(self) -> None:
        if not self.role or self.role != self.role.strip() or "\n" in self.role or "\r" in self.role:
            raise ValueError("evidence role must be non-empty, trimmed, and single-line")
        if self.digest_algorithm != "sha256":
            raise ValueError("unsupported evidence digest algorithm")
        if len(self.digest) != 64 or any(ch not in "0123456789abcdef" for ch in self.digest):
            raise ValueError("evidence digest must be lowercase SHA-256 hex")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("evidence size must be non-negative")
        if self.media_type is not None and (
            not self.media_type
            or self.media_type != self.media_type.strip()
            or "\n" in self.media_type
            or "\r" in self.media_type
        ):
            raise ValueError("evidence media type must be non-empty, trimmed, and single-line")
        if self.storage_ref is not None and (
            not self.storage_ref
            or self.storage_ref != self.storage_ref.strip()
            or "\n" in self.storage_ref
            or "\r" in self.storage_ref
        ):
            raise ValueError("evidence storage reference must be non-empty, trimmed, and single-line")

    @property
    def portable_identity(self) -> tuple[str, str, str, str | None, int | None]:
        """Return identity independent of the physical storage locator."""

        return (self.role, self.digest_algorithm, self.digest, self.media_type, self.size_bytes)

    @classmethod
    def from_execution_reference(
        cls,
        *,
        run_id: RunId,
        cell_id: str | None,
        reference: ExecutionEvidenceReference,
    ) -> StoredEvidenceRef:
        """Losslessly wrap a portable kernel evidence reference for durable storage."""

        if reference.portable_identity is None:
            raise ValueError("durable evidence requires portable content identity")
        assert reference.digest_algorithm is not None
        assert reference.digest is not None
        assert reference.size_bytes is not None
        return cls(
            run_id=run_id,
            cell_id=cell_id,
            role=reference.kind,
            digest_algorithm=reference.digest_algorithm,
            digest=reference.digest,
            media_type=reference.media_type,
            size_bytes=reference.size_bytes,
            storage_ref=reference.ref,
        )

    def to_execution_reference(self) -> ExecutionEvidenceReference:
        """Map durable execution evidence back to the portable kernel representation."""

        if self.role not in {"log", "metric", "trace", "lineage", "output", "resource", "cost"}:
            raise ValueError("stored role is not a kernel execution evidence kind")
        if self.size_bytes is None or self.storage_ref is None:
            raise ValueError("stored evidence is unavailable as a portable execution reference")
        return ExecutionEvidenceReference(
            self.role,  # type: ignore[arg-type]
            self.storage_ref,
            self.digest_algorithm,
            self.digest,
            self.media_type,
            self.size_bytes,
        )


class JobStore(Protocol):
    def create_job(self, job: Job, run: Run) -> Job: ...

    def get_job(self, job_id: JobId) -> Job | None: ...

    def get_run_id_for_job(self, job_id: JobId) -> RunId | None: ...

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page: ...

    def request_cancel(self, job_id: JobId, *, now: Instant) -> Job: ...

    def claim_next_run(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: Instant,
    ) -> ClaimedRun | None: ...

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant,
        now: Instant,
    ) -> bool: ...

    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...

    def read_event_page(
        self,
        run_id: RunId,
        *,
        since: str | None,
        limit: int,
    ) -> EventPage: ...

    def read_events(
        self,
        run_id: RunId,
        *,
        since: int,
    ) -> tuple[StoredExecutionEvent, ...]: ...

    def put_cell_result(
        self,
        attempt_id: AttemptId,
        result: StoredCellResult,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...

    def read_cell_results(self, run_id: RunId) -> tuple[StoredCellResult, ...]: ...

    def put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...

    def read_evidence(self, run_id: RunId) -> tuple[StoredEvidenceRef, ...]: ...

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        state: AttemptState,
        failure_code: str | None,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...

    def reclaim_expired(self, *, now: Instant) -> tuple[RunId, ...]: ...


__all__ = [
    "ClaimedRun",
    "EventPage",
    "JobStore",
    "Page",
    "RunExecutionEvent",
    "StoredCellResult",
    "StoredEvidenceRef",
    "StoredExecutionEvent",
]
