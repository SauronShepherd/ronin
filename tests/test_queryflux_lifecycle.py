from concurrent.futures import ThreadPoolExecutor

import pytest
from studio_data_engineering.queryflux_lifecycle import (
    QueryFluxExecution,
    SqliteQueryFluxExecutionStore,
)


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


def test_sqlite_queryflux_store_is_idempotent_and_persists_cancel(tmp_path) -> None:
    store = SqliteQueryFluxExecutionStore(tmp_path / "ronin.db")
    created = store.create(_execution())
    assert store.create(_execution()) == created
    cancelling = store.request_cancel(created)
    assert cancelling.state == "cancelling"
    assert cancelling.cancel_requested is True
    assert store.get("workspace-a", "project-a", "run-a", "attempt-a") == cancelling
    assert store.request_cancel(cancelling) == cancelling


def test_sqlite_queryflux_store_rejects_transition_for_missing_execution(tmp_path) -> None:
    store = SqliteQueryFluxExecutionStore(tmp_path / "ronin.db")
    with pytest.raises(KeyError, match="does not exist"):
        store.request_cancel(_execution())


def test_sqlite_queryflux_store_serializes_cancel_and_terminal_transition(tmp_path) -> None:
    path = tmp_path / "ronin.db"
    seed = SqliteQueryFluxExecutionStore(path)
    seed.create(_execution().transition("running"))

    def finish() -> QueryFluxExecution | None:
        try:
            return SqliteQueryFluxExecutionStore(path).transition(
                _execution().transition("running").transition("succeeded")
            )
        except ValueError:
            return None

    def cancel() -> QueryFluxExecution:
        return SqliteQueryFluxExecutionStore(path).request_cancel(
            _execution().transition("running")
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [future.result() for future in (pool.submit(finish), pool.submit(cancel))]

    final = SqliteQueryFluxExecutionStore(path).get(
        "workspace-a", "project-a", "run-a", "attempt-a"
    )
    assert final is not None
    assert final.state in {"succeeded", "cancelling"}
    assert not (final.state == "succeeded" and final.cancel_requested)
    assert all(
        outcome is None or outcome.state in {"succeeded", "cancelling", "cancelled"}
        for outcome in outcomes
    )
