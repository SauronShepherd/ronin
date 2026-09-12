"""Storage-neutral durable execution port."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
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


class EvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    TOMBSTONED = "tombstoned"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class StoredEvidenceRef:
    """Run/cell ownership wrapped around storage-neutral evidence identity."""

    run_id: RunId
    cell_id: str | None
    role: str
    digest_algorithm: str | None
    digest: str | None
    media_type: str | None
    size_bytes: int | None
    storage_ref: str | None
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.role
            or self.role != self.role.strip()
            or "\n" in self.role
            or "\r" in self.role
        ):
            raise ValueError("evidence role must be non-empty, trimmed, and single-line")
        availability = EvidenceAvailability(self.availability)
        object.__setattr__(self, "availability", availability)
        identity = (self.digest_algorithm, self.digest, self.size_bytes)
        if availability is EvidenceAvailability.UNAVAILABLE:
            if any(value is not None for value in identity) or self.storage_ref is not None:
                raise ValueError("unavailable evidence cannot carry content identity or locator")
            if (
                self.unavailable_reason is None
                or not self.unavailable_reason
                or self.unavailable_reason != self.unavailable_reason.strip()
                or "\n" in self.unavailable_reason
                or "\r" in self.unavailable_reason
                or len(self.unavailable_reason) > 256
            ):
                raise ValueError("unavailable evidence requires a bounded trimmed reason")
            return
        if any(value is None for value in identity):
            raise ValueError("available, missing, and tombstoned evidence require content identity")
        if self.digest_algorithm != "sha256":
            raise ValueError("unsupported evidence digest algorithm")
        digest = self.digest
        size_bytes = self.size_bytes
        if (
            digest is None
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ValueError("evidence digest must be lowercase SHA-256 hex")
        if size_bytes is None or size_bytes < 0:
            raise ValueError("evidence size must be non-negative")
        if self.unavailable_reason is not None:
            raise ValueError("only unavailable evidence may carry an unavailable reason")
        if availability is not EvidenceAvailability.AVAILABLE and self.storage_ref is not None:
            raise ValueError("non-available evidence must not carry a physical locator")
        if availability is EvidenceAvailability.AVAILABLE and self.storage_ref is None:
            raise ValueError("available evidence requires a physical locator")

    @property
    def portable_identity(self) -> tuple[str, str, str, str | None, int] | None:
        """Return logical content identity independent of physical location/state."""

        if self.digest_algorithm is None or self.digest is None or self.size_bytes is None:
            return None
        return (self.role, self.digest_algorithm, self.digest, self.media_type, self.size_bytes)

    @classmethod
    def from_execution_reference(
        cls,
        *,
        run_id: RunId,
        cell_id: str | None,
        reference: ExecutionEvidenceReference,
    ) -> StoredEvidenceRef:
        """Losslessly wrap an available portable kernel evidence reference."""

        digest_algorithm = reference.digest_algorithm
        digest = reference.digest
        size_bytes = reference.size_bytes
        if digest_algorithm is None or digest is None or size_bytes is None:
            raise ValueError("durable evidence requires portable content identity")
        return cls(
            run_id=run_id,
            cell_id=cell_id,
            role=reference.kind,
            digest_algorithm=digest_algorithm,
            digest=digest,
            media_type=reference.media_type,
            size_bytes=size_bytes,
            storage_ref=reference.ref,
            availability=EvidenceAvailability.AVAILABLE,
        )

    def public_payload(self) -> dict[str, object]:
        """Return v1 public evidence without backend-private locator metadata."""

        return {
            "version": 1,
            "cell_id": self.cell_id,
            "role": self.role,
            "availability": self.availability.value,
            "digest_algorithm": self.digest_algorithm,
            "digest": self.digest,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "reason": self.unavailable_reason,
        }

    def to_execution_reference(self) -> ExecutionEvidenceReference:
        """Map available durable evidence back to the portable kernel representation."""

        if self.availability is not EvidenceAvailability.AVAILABLE:
            raise ValueError("stored evidence is not currently available")
        if self.role not in {"log", "metric", "trace", "lineage", "output", "resource", "cost"}:
            raise ValueError("stored role is not a kernel execution evidence kind")
        if (
            self.digest_algorithm is None
            or self.digest is None
            or self.size_bytes is None
            or self.storage_ref is None
        ):
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
    "EvidenceAvailability",
    "JobStore",
    "Page",
    "RunExecutionEvent",
    "StoredCellResult",
    "StoredEvidenceRef",
    "StoredExecutionEvent",
]
