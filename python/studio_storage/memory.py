"""Concurrent in-memory reference adapter for the durable JobStore contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock

from studio_orchestrator import (
    Attempt,
    AttemptId,
    AttemptLimitExceeded,
    AttemptState,
    ClaimedRun,
    Job,
    JobId,
    JobState,
    Lease,
    LeaseToken,
    Page,
    Run,
    RunId,
    RunState,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)


class IdempotencyConflict(ValueError):
    """Raised when one idempotency key is reused for different request content."""


def _add_seconds(value: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed + timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


class InMemoryJobStore:
    """Reference store with the same atomic semantics expected from SQLite."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[JobId, Job] = {}
        self._runs: dict[RunId, Run] = {}
        self._attempts: dict[AttemptId, Attempt] = {}
        self._idempotency: dict[tuple[str, str], JobId] = {}
        self._events: dict[AttemptId, list[StoredExecutionEvent]] = {}
        self._cell_results: dict[RunId, dict[str, StoredCellResult]] = {}
        self._evidence: dict[RunId, list[StoredEvidenceRef]] = {}

    def create_job(self, job: Job, run: Run) -> Job:
        with self._lock:
            key = (job.project_id, job.idempotency_key)
            existing_id = self._idempotency.get(key)
            if existing_id is not None:
                existing = self._jobs[existing_id]
                if existing.request_digest != job.request_digest:
                    raise IdempotencyConflict("idempotency key already exists for different request")
                return existing
            if job.id in self._jobs or run.id in self._runs:
                raise ValueError("job or run identity already exists")
            if run.job_id != job.id:
                raise ValueError("run must belong to job")
            self._jobs[job.id] = job
            self._runs[run.id] = run
            self._idempotency[key] = job.id
            return job

    def get_job(self, job_id: JobId) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        offset = int(cursor) if cursor is not None else 0
        with self._lock:
            values = sorted(self._jobs.values(), key=lambda item: str(item.id))
            values = [
                item
                for item in values
                if (project_id is None or item.project_id == project_id)
                and (state is None or item.state is state)
            ]
            items = tuple(values[offset : offset + limit])
            next_offset = offset + len(items)
            next_cursor = str(next_offset) if next_offset < len(values) else None
            return Page(items, next_cursor)

    def request_cancel(self, job_id: JobId, *, now: str) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            if job.state.terminal:
                return job
            active = any(
                attempt.state in {AttemptState.LEASED, AttemptState.RUNNING}
                and self._runs[attempt.run_id].job_id == job_id
                for attempt in self._attempts.values()
            )
            if active:
                updated = job.transition(JobState.CANCELLING, now=now)
                self._jobs[job_id] = updated
                for run_id, run in tuple(self._runs.items()):
                    if run.job_id == job_id and run.state in {RunState.LEASED, RunState.RUNNING}:
                        self._runs[run_id] = run.transition(RunState.CANCELLING, now=now)
                return updated
            for run_id, run in tuple(self._runs.items()):
                if run.job_id == job_id and not run.state.terminal:
                    if run.state is RunState.PENDING:
                        self._runs[run_id] = run.transition(RunState.CANCELLED, now=now)
                    else:
                        cancelling = run.transition(RunState.CANCELLING, now=now)
                        self._runs[run_id] = cancelling.transition(RunState.CANCELLED, now=now)
            if job.state is JobState.QUEUED:
                updated = job.transition(JobState.CANCELLED, now=now)
            else:
                cancelling = job.transition(JobState.CANCELLING, now=now)
                updated = cancelling.transition(JobState.CANCELLED, now=now)
            self._jobs[job_id] = updated
            return updated

    def claim_next_run(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: str,
    ) -> ClaimedRun | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        with self._lock:
            candidates = sorted(
                (
                    run
                    for run in self._runs.values()
                    if run.state is RunState.PENDING and run.not_before <= now
                ),
                key=lambda run: (run.not_before, str(run.id)),
            )
            if not candidates:
                return None
            run = candidates[0]
            job = self._jobs[run.job_id]
            if job.state is not JobState.QUEUED:
                return None
            ordinal = 1 + max(
                (attempt.ordinal for attempt in self._attempts.values() if attempt.run_id == run.id),
                default=0,
            )
            if ordinal > 10:
                failed_run = run.transition(RunState.FAILED, now=now)
                failed_job = job.transition(
                    JobState.RUNNING, now=now
                ).transition(JobState.FAILED, now=now, failure_code="attempt_limit_exceeded")
                self._runs[run.id] = failed_run
                self._jobs[job.id] = failed_job
                raise AttemptLimitExceeded("attempt limit exceeded")
            lease = Lease(
                owner=owner,
                token=lease_token,
                acquired_at=now,
                expires_at=_add_seconds(now, lease_seconds),
                heartbeat_at=now,
            )
            attempt = Attempt(
                id=attempt_id,
                run_id=run.id,
                ordinal=ordinal,
                state=AttemptState.LEASED,
                lease=lease,
                created_at=now,
                updated_at=now,
            )
            self._attempts[attempt_id] = attempt
            self._events[attempt_id] = []
            self._runs[run.id] = run.transition(RunState.LEASED, now=now)
            self._jobs[job.id] = job.transition(JobState.RUNNING, now=now)
            return ClaimedRun(job=self._jobs[job.id], run=self._runs[run.id], attempt_id=attempt_id, attempt_ordinal=ordinal, lease_token=lease_token)

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: str,
        now: str,
    ) -> bool:
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None or attempt.state not in {AttemptState.LEASED, AttemptState.RUNNING}:
                return False
            if attempt.lease is None or attempt.lease.expires_at <= now:
                return False
            try:
                lease = attempt.lease.renew(
                    owner=owner,
                    token=lease_token,
                    expires_at=expires_at,
                    now=now,
                )
            except ValueError:
                return False
            self._attempts[attempt_id] = Attempt(
                id=attempt.id,
                run_id=attempt.run_id,
                ordinal=attempt.ordinal,
                state=attempt.state,
                lease=lease,
                created_at=attempt.created_at,
                updated_at=now,
                failure_code=attempt.failure_code,
            )
            return True

    def append_events(
        self,
        attempt_id: AttemptId,
        events: list[StoredExecutionEvent] | tuple[StoredExecutionEvent, ...],
    ) -> None:
        with self._lock:
            target = self._events[attempt_id]
            expected = len(target)
            for event in events:
                if event.attempt_id != attempt_id or event.sequence != expected:
                    raise ValueError("event sequence must be contiguous within attempt")
                target.append(event)
                expected += 1

    def read_events(self, run_id: RunId, *, since: int) -> tuple[StoredExecutionEvent, ...]:
        if since < 0:
            raise ValueError("since must be non-negative")
        with self._lock:
            attempts = sorted(
                (attempt for attempt in self._attempts.values() if attempt.run_id == run_id),
                key=lambda item: item.ordinal,
            )
            merged = tuple(event for attempt in attempts for event in self._events[attempt.id])
            return merged[since:]

    def put_cell_result(self, result: StoredCellResult) -> None:
        with self._lock:
            self._cell_results.setdefault(result.run_id, {})[result.cell_id] = result

    def read_cell_results(self, run_id: RunId) -> tuple[StoredCellResult, ...]:
        with self._lock:
            return tuple(
                self._cell_results.get(run_id, {})[cell_id]
                for cell_id in sorted(self._cell_results.get(run_id, {}))
            )

    def put_evidence(self, ref: StoredEvidenceRef) -> None:
        with self._lock:
            self._evidence.setdefault(ref.run_id, []).append(ref)

    def read_evidence(self, run_id: RunId) -> tuple[StoredEvidenceRef, ...]:
        with self._lock:
            return tuple(self._evidence.get(run_id, ()))

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        state: AttemptState,
        failure_code: str | None,
        owner: str,
        lease_token: LeaseToken,
        now: str,
    ) -> None:
        if not state.terminal:
            raise ValueError("attempt completion state must be terminal")
        with self._lock:
            attempt = self._attempts[attempt_id]
            if attempt.lease is None or attempt.lease.owner != owner or attempt.lease.token != lease_token:
                raise ValueError("attempt lease ownership lost")
            completed = attempt.transition(state, now=now, failure_code=failure_code)
            self._attempts[attempt_id] = completed
            run = self._runs[attempt.run_id]
            job = self._jobs[run.job_id]
            if state is AttemptState.ABANDONED:
                self._runs[run.id] = run.transition(RunState.PENDING, now=now)
                return
            if state is AttemptState.SUCCEEDED:
                self._runs[run.id] = run.transition(RunState.SUCCEEDED, now=now)
                self._jobs[job.id] = job.transition(JobState.SUCCEEDED, now=now)
                return
            if state is AttemptState.CANCELLED:
                run_state = RunState.CANCELLED
                job_state = JobState.CANCELLED
            else:
                run_state = RunState.FAILED
                job_state = JobState.FAILED
            if run.state is RunState.CANCELLING and run_state is RunState.CANCELLED:
                next_run = run.transition(RunState.CANCELLED, now=now)
            else:
                next_run = run.transition(run_state, now=now)
            if job.state is JobState.CANCELLING and job_state is JobState.CANCELLED:
                next_job = job.transition(JobState.CANCELLED, now=now)
            else:
                next_job = job.transition(job_state, now=now, failure_code=failure_code)
            self._runs[run.id] = next_run
            self._jobs[job.id] = next_job

    def reclaim_expired(self, *, now: str) -> tuple[RunId, ...]:
        reclaimed: list[RunId] = []
        with self._lock:
            for attempt_id, attempt in tuple(self._attempts.items()):
                if (
                    attempt.state in {AttemptState.LEASED, AttemptState.RUNNING}
                    and attempt.lease is not None
                    and attempt.lease.expires_at <= now
                ):
                    self._attempts[attempt_id] = attempt.transition(AttemptState.ABANDONED, now=now)
                    run = self._runs[attempt.run_id]
                    self._runs[run.id] = run.transition(RunState.PENDING, now=now)
                    reclaimed.append(run.id)
            return tuple(reclaimed)


__all__ = ["IdempotencyConflict", "InMemoryJobStore"]
