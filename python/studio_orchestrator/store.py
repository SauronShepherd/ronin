"""Storage-neutral durable execution port."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

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
    occurred_at: str


@dataclass(frozen=True, slots=True)
class StoredCellResult:
    run_id: RunId
    cell_id: str
    source_digest: str
    execution_identity_digest: str
    state: str
    result_json: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class StoredEvidenceRef:
    run_id: RunId
    cell_id: str | None
    role: str
    digest_algorithm: str
    digest: str
    media_type: str | None
    size_bytes: int | None
    storage_ref: str | None


class JobStore(Protocol):
    def create_job(self, job: Job, run: Run) -> Job: ...

    def get_job(self, job_id: JobId) -> Job | None: ...

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page: ...

    def request_cancel(self, job_id: JobId, *, now: str) -> Job: ...

    def claim_next_run(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: str,
    ) -> ClaimedRun | None: ...

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: str,
        now: str,
    ) -> bool: ...

    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
    ) -> None: ...

    def read_events(
        self,
        run_id: RunId,
        *,
        since: int,
    ) -> tuple[StoredExecutionEvent, ...]: ...

    def put_cell_result(self, result: StoredCellResult) -> None: ...

    def read_cell_results(self, run_id: RunId) -> tuple[StoredCellResult, ...]: ...

    def put_evidence(self, ref: StoredEvidenceRef) -> None: ...

    def read_evidence(self, run_id: RunId) -> tuple[StoredEvidenceRef, ...]: ...

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        state: AttemptState,
        failure_code: str | None,
        owner: str,
        lease_token: LeaseToken,
        now: str,
    ) -> None: ...

    def reclaim_expired(self, *, now: str) -> tuple[RunId, ...]: ...


__all__ = [
    "ClaimedRun",
    "JobStore",
    "Page",
    "StoredCellResult",
    "StoredEvidenceRef",
    "StoredExecutionEvent",
]
