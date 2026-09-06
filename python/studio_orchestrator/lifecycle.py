"""Pure Job -> Run -> Attempt lifecycle contracts for durable execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum


class LifecycleError(ValueError):
    """Base error for invalid durable-lifecycle operations."""


class InvalidTransition(LifecycleError):
    """Raised when a lifecycle transition is not legal."""


class LeaseLost(LifecycleError):
    """Raised when a worker no longer owns an attempt lease."""


class AttemptLimitExceeded(LifecycleError):
    """Raised when crash-reclaim attempts exceed the hard v0.1 cap."""


def _require_text(name: str, value: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    if len(value) > 256:
        raise ValueError(f"{name} must be at most 256 characters")
    return value


@dataclass(frozen=True, slots=True, order=True)
class JobId:
    value: str

    def __post_init__(self) -> None:
        _require_text("job id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class RunId:
    value: str

    def __post_init__(self) -> None:
        _require_text("run id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class AttemptId:
    value: str

    def __post_init__(self) -> None:
        _require_text("attempt id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class LeaseToken:
    value: str

    def __post_init__(self) -> None:
        _require_text("lease token", self.value)

    def __str__(self) -> str:
        return self.value


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {self.CANCELLED, self.SUCCEEDED, self.FAILED}


class RunState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {self.CANCELLED, self.SUCCEEDED, self.FAILED}


class AttemptState(StrEnum):
    LEASED = "leased"
    RUNNING = "running"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {self.ABANDONED, self.CANCELLED, self.SUCCEEDED, self.FAILED}


_JOB_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLING, JobState.CANCELLED}),
    JobState.RUNNING: frozenset({JobState.CANCELLING, JobState.SUCCEEDED, JobState.FAILED}),
    JobState.CANCELLING: frozenset({JobState.CANCELLED, JobState.FAILED}),
    JobState.CANCELLED: frozenset(),
    JobState.SUCCEEDED: frozenset(),
    JobState.FAILED: frozenset(),
}

_RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.PENDING: frozenset(
        {RunState.LEASED, RunState.CANCELLING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.LEASED: frozenset({RunState.RUNNING, RunState.PENDING, RunState.CANCELLING}),
    RunState.RUNNING: frozenset(
        {RunState.PENDING, RunState.CANCELLING, RunState.SUCCEEDED, RunState.FAILED}
    ),
    RunState.CANCELLING: frozenset({RunState.CANCELLED, RunState.FAILED}),
    RunState.CANCELLED: frozenset(),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
}

_ATTEMPT_TRANSITIONS: dict[AttemptState, frozenset[AttemptState]] = {
    AttemptState.LEASED: frozenset(
        {AttemptState.RUNNING, AttemptState.ABANDONED, AttemptState.CANCELLED}
    ),
    AttemptState.RUNNING: frozenset(
        {
            AttemptState.ABANDONED,
            AttemptState.CANCELLED,
            AttemptState.SUCCEEDED,
            AttemptState.FAILED,
        }
    ),
    AttemptState.ABANDONED: frozenset(),
    AttemptState.CANCELLED: frozenset(),
    AttemptState.SUCCEEDED: frozenset(),
    AttemptState.FAILED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """v0.1 ordinary retry and crash-replacement limits."""

    max_runs: int = 1
    max_attempts: int = 10

    def __post_init__(self) -> None:
        if self.max_runs < 1:
            raise ValueError("max_runs must be positive")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")


@dataclass(frozen=True, slots=True)
class Lease:
    owner: str
    token: LeaseToken
    acquired_at: str
    expires_at: str
    heartbeat_at: str

    def __post_init__(self) -> None:
        _require_text("lease owner", self.owner)
        _require_text("acquired_at", self.acquired_at)
        _require_text("expires_at", self.expires_at)
        _require_text("heartbeat_at", self.heartbeat_at)

    def renew(
        self,
        *,
        owner: str,
        token: LeaseToken,
        expires_at: str,
        now: str,
    ) -> Lease:
        if owner != self.owner or token != self.token:
            raise LeaseLost("lease ownership no longer matches")
        _require_text("expires_at", expires_at)
        _require_text("now", now)
        return replace(self, expires_at=expires_at, heartbeat_at=now)


@dataclass(frozen=True, slots=True)
class Job:
    id: JobId
    project_id: str
    idempotency_key: str
    request_digest: str
    state: JobState
    created_at: str
    updated_at: str
    failure_code: str | None = None
    target: str = ""
    parameters_json: str = "{}"

    def __post_init__(self) -> None:
        _require_text("project id", self.project_id)
        _require_text("idempotency key", self.idempotency_key)
        _require_text("request digest", self.request_digest)
        _require_text("created_at", self.created_at)
        _require_text("updated_at", self.updated_at)
        if self.failure_code is not None:
            _require_text("failure code", self.failure_code)
        if self.target:
            _require_text("target", self.target)
        try:
            parameters = json.loads(self.parameters_json)
        except json.JSONDecodeError as exc:
            raise ValueError("parameters_json must be valid JSON") from exc
        if not isinstance(parameters, dict):
            raise ValueError("parameters_json must encode a JSON object")

    def transition(
        self,
        target: JobState,
        *,
        now: str,
        failure_code: str | None = None,
    ) -> Job:
        if target not in _JOB_TRANSITIONS[self.state]:
            raise InvalidTransition(f"job {self.state.value} -> {target.value} is not legal")
        _require_text("now", now)
        if failure_code is not None:
            _require_text("failure code", failure_code)
        return replace(self, state=target, updated_at=now, failure_code=failure_code)


@dataclass(frozen=True, slots=True)
class Run:
    id: RunId
    job_id: JobId
    ordinal: int
    state: RunState
    not_before: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise ValueError("run ordinal must be positive")
        _require_text("not_before", self.not_before)
        _require_text("created_at", self.created_at)
        _require_text("updated_at", self.updated_at)

    def transition(self, target: RunState, *, now: str) -> Run:
        if target not in _RUN_TRANSITIONS[self.state]:
            raise InvalidTransition(f"run {self.state.value} -> {target.value} is not legal")
        _require_text("now", now)
        return replace(self, state=target, updated_at=now)


@dataclass(frozen=True, slots=True)
class Attempt:
    id: AttemptId
    run_id: RunId
    ordinal: int
    state: AttemptState
    lease: Lease | None
    created_at: str
    updated_at: str
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.ordinal <= 10:
            raise AttemptLimitExceeded("attempt ordinal must be between 1 and 10")
        _require_text("created_at", self.created_at)
        _require_text("updated_at", self.updated_at)
        if self.failure_code is not None:
            _require_text("failure code", self.failure_code)

    def transition(
        self,
        target: AttemptState,
        *,
        now: str,
        failure_code: str | None = None,
    ) -> Attempt:
        if target not in _ATTEMPT_TRANSITIONS[self.state]:
            raise InvalidTransition(f"attempt {self.state.value} -> {target.value} is not legal")
        _require_text("now", now)
        if failure_code is not None:
            _require_text("failure code", failure_code)
        lease = None if target.terminal else self.lease
        return replace(
            self,
            state=target,
            updated_at=now,
            failure_code=failure_code,
            lease=lease,
        )


__all__ = [
    "Attempt",
    "AttemptId",
    "AttemptLimitExceeded",
    "AttemptState",
    "InvalidTransition",
    "Job",
    "JobId",
    "JobState",
    "Lease",
    "LeaseLost",
    "LeaseToken",
    "LifecycleError",
    "RetryPolicy",
    "Run",
    "RunId",
    "RunState",
]
