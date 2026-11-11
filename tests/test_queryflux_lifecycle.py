import pytest
from studio_data_engineering.queryflux_lifecycle import QueryFluxExecution


def _execution() -> QueryFluxExecution:
    return QueryFluxExecution("workspace-a", "project-a", "run-a", "attempt-a")


def test_queryflux_lifecycle_allows_bounded_terminal_paths() -> None:
    running = _execution().transition("running")
    assert running.transition("succeeded").terminal is True
    assert _execution().request_cancel().transition("cancelled").state == "cancelled"
    failed = running.transition("failed", failure_code="provider_timeout")
    assert failed.failure_code == "provider_timeout"


def test_queryflux_cancel_is_idempotent_and_terminal_state_is_immutable() -> None:
    cancelling = _execution().request_cancel()
    assert cancelling.request_cancel() == cancelling
    cancelled = cancelling.transition("cancelled")
    assert cancelled.request_cancel() == cancelled


@pytest.mark.parametrize("state", ["queued", "running", "cancelling"])
def test_queryflux_cancellation_never_reports_success(state: str) -> None:
    execution = _execution().transition(state) if state != "queued" else _execution()
    with pytest.raises(ValueError, match="cannot succeed"):
        execution.request_cancel().transition("succeeded")


def test_queryflux_failed_state_requires_failure_code() -> None:
    with pytest.raises(ValueError, match="failure_code"):
        _execution().transition("failed")


def test_queryflux_rejects_illegal_transition() -> None:
    with pytest.raises(ValueError, match="invalid QueryFlux transition"):
        _execution().transition("succeeded")
