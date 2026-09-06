from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from studio_orchestrator import (
    Attempt,
    AttemptId,
    AttemptLimitExceeded,
    AttemptState,
    InvalidTransition,
    Job,
    JobId,
    JobState,
    Lease,
    LeaseLost,
    LeaseToken,
    RetryPolicy,
    Run,
    RunId,
    RunState,
)

NOW = "2026-09-06T09:00:00Z"
LATER = "2026-09-06T09:00:10Z"
EXPIRY = "2026-09-06T09:00:30Z"


def make_job(state: JobState = JobState.QUEUED) -> Job:
    return Job(
        id=JobId("job-1"),
        project_id="project-1",
        idempotency_key="key-1",
        request_digest="a" * 64,
        state=state,
        created_at=NOW,
        updated_at=NOW,
    )


def make_run(state: RunState = RunState.PENDING) -> Run:
    return Run(
        id=RunId("run-1"),
        job_id=JobId("job-1"),
        ordinal=1,
        state=state,
        not_before=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def make_lease() -> Lease:
    return Lease(
        owner="worker-1",
        token=LeaseToken("token-1"),
        acquired_at=NOW,
        expires_at=EXPIRY,
        heartbeat_at=NOW,
    )


def make_attempt(state: AttemptState = AttemptState.LEASED) -> Attempt:
    return Attempt(
        id=AttemptId("attempt-1"),
        run_id=RunId("run-1"),
        ordinal=1,
        state=state,
        lease=None if state.terminal else make_lease(),
        created_at=NOW,
        updated_at=NOW,
    )


def test_identifiers_are_validated_ordered_and_immutable() -> None:
    assert str(JobId("job-1")) == "job-1"
    assert str(RunId("run-1")) == "run-1"
    assert str(AttemptId("attempt-1")) == "attempt-1"
    assert str(LeaseToken("token-1")) == "token-1"
    assert JobId("job-1") < JobId("job-2")
    with pytest.raises(FrozenInstanceError):
        JobId("job-1").value = "other"  # type: ignore[misc]


@pytest.mark.parametrize("value", ["", " x", "x ", "x\n", "x\r", "x" * 257])
def test_identifier_rejects_invalid_text(value: str) -> None:
    with pytest.raises(ValueError, match="must be|at most"):
        JobId(value)


def test_state_terminal_predicates_match_contract() -> None:
    assert JobState.CANCELLED.terminal
    assert not JobState.QUEUED.terminal
    assert RunState.SUCCEEDED.terminal
    assert not RunState.PENDING.terminal
    assert AttemptState.ABANDONED.terminal
    assert not AttemptState.RUNNING.terminal


def test_retry_policy_defaults_and_bounds() -> None:
    assert RetryPolicy() == RetryPolicy(max_runs=1, max_attempts=10)
    with pytest.raises(ValueError, match="max_runs"):
        RetryPolicy(max_runs=0)
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=11)


def test_lease_renews_only_for_current_owner_and_token() -> None:
    lease = make_lease()
    renewed = lease.renew(
        owner="worker-1",
        token=LeaseToken("token-1"),
        expires_at="2026-09-06T09:00:40Z",
        now=LATER,
    )
    assert renewed.heartbeat_at == LATER
    assert renewed.expires_at == "2026-09-06T09:00:40Z"
    with pytest.raises(LeaseLost):
        lease.renew(
            owner="worker-2",
            token=LeaseToken("token-1"),
            expires_at=EXPIRY,
            now=LATER,
        )
    with pytest.raises(LeaseLost):
        lease.renew(
            owner="worker-1",
            token=LeaseToken("token-2"),
            expires_at=EXPIRY,
            now=LATER,
        )


def test_job_intended_paths_reach_terminal_states() -> None:
    assert (
        make_job()
        .transition(JobState.RUNNING, now=LATER)
        .transition(JobState.SUCCEEDED, now=EXPIRY)
        .state
        is JobState.SUCCEEDED
    )
    assert (
        make_job()
        .transition(JobState.RUNNING, now=LATER)
        .transition(JobState.FAILED, now=EXPIRY, failure_code="cell_failed")
        .failure_code
        == "cell_failed"
    )
    assert (
        make_job()
        .transition(JobState.CANCELLING, now=LATER)
        .transition(JobState.CANCELLED, now=EXPIRY)
        .state
        is JobState.CANCELLED
    )
    assert make_job().transition(JobState.CANCELLED, now=LATER).state is JobState.CANCELLED


@pytest.mark.parametrize("state", [JobState.CANCELLED, JobState.SUCCEEDED, JobState.FAILED])
def test_job_terminal_states_reject_every_transition(state: JobState) -> None:
    for target in JobState:
        with pytest.raises(InvalidTransition):
            make_job(state).transition(target, now=LATER)


def test_run_reclaim_path_preserves_identity() -> None:
    run = make_run().transition(RunState.LEASED, now=LATER)
    reclaimed = run.transition(RunState.PENDING, now=EXPIRY)
    assert reclaimed.id == run.id
    assert reclaimed.job_id == run.job_id
    assert reclaimed.state is RunState.PENDING
    assert make_run().transition(RunState.FAILED, now=LATER).state is RunState.FAILED


@pytest.mark.parametrize("state", [RunState.CANCELLED, RunState.SUCCEEDED, RunState.FAILED])
def test_run_terminal_states_reject_every_transition(state: RunState) -> None:
    for target in RunState:
        with pytest.raises(InvalidTransition):
            make_run(state).transition(target, now=LATER)


def test_attempt_paths_clear_lease_on_terminal_state() -> None:
    running = make_attempt().transition(AttemptState.RUNNING, now=LATER)
    succeeded = running.transition(AttemptState.SUCCEEDED, now=EXPIRY)
    assert succeeded.lease is None
    assert succeeded.state is AttemptState.SUCCEEDED
    failed = make_attempt(AttemptState.RUNNING).transition(
        AttemptState.FAILED,
        now=EXPIRY,
        failure_code="cell_failed",
    )
    assert failed.failure_code == "cell_failed"
    assert make_attempt().transition(AttemptState.ABANDONED, now=LATER).lease is None
    assert make_attempt().transition(AttemptState.CANCELLED, now=LATER).lease is None


@pytest.mark.parametrize(
    "state",
    [
        AttemptState.ABANDONED,
        AttemptState.CANCELLED,
        AttemptState.SUCCEEDED,
        AttemptState.FAILED,
    ],
)
def test_attempt_terminal_states_reject_every_transition(state: AttemptState) -> None:
    for target in AttemptState:
        with pytest.raises(InvalidTransition):
            make_attempt(state).transition(target, now=LATER)


def test_attempt_cap_is_hard_and_distinct() -> None:
    with pytest.raises(AttemptLimitExceeded):
        Attempt(
            id=AttemptId("attempt-11"),
            run_id=RunId("run-1"),
            ordinal=11,
            state=AttemptState.LEASED,
            lease=make_lease(),
            created_at=NOW,
            updated_at=NOW,
        )


def test_domain_value_validation_failures() -> None:
    with pytest.raises(ValueError, match="project id"):
        make_job().__class__(JobId("job-x"), "", "key", "a" * 64, JobState.QUEUED, NOW, NOW)
    with pytest.raises(ValueError, match="run ordinal"):
        Run(RunId("run-x"), JobId("job-x"), 0, RunState.PENDING, NOW, NOW, NOW)
    with pytest.raises(ValueError, match="lease owner"):
        Lease("", LeaseToken("token"), NOW, EXPIRY, NOW)
