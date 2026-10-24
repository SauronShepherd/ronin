import multiprocessing

import pytest
from studio_quality import PredicateSandboxError, evaluate_python_predicate


def test_quality_python_predicate_is_bounded_and_boolean() -> None:
    rows = ({"amount": 2}, {"amount": 3})
    assert evaluate_python_predicate("all(row['amount'] > 0 for row in rows)", rows)
    with pytest.raises(PredicateSandboxError, match="boolean"):
        evaluate_python_predicate("len(rows)", rows)


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "rows[0].get('amount')", "open('secret')"],
)
def test_quality_python_predicate_rejects_escape_hatches(expression: str) -> None:
    with pytest.raises(PredicateSandboxError):
        evaluate_python_predicate(expression, ({"amount": 1},))


def test_quality_python_predicate_rejects_unbounded_input() -> None:
    with pytest.raises(PredicateSandboxError, match="row limit"):
        evaluate_python_predicate("True", ({"x": 1},) * 3, max_rows=2)


def test_quality_python_predicate_timeout_terminates_worker_process() -> None:
    rows = tuple({"amount": 1} for _ in range(10_000))

    with pytest.raises(PredicateSandboxError, match="timed out"):
        evaluate_python_predicate(
            "all(all(row['amount'] > 0 for row in rows) for row in rows)",
            rows,
            timeout_seconds=2.0,
        )

    assert not any(
        process.name == "quality-predicate" for process in multiprocessing.active_children()
    )


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0, -1])
def test_quality_python_predicate_rejects_invalid_timeouts(timeout: float) -> None:
    with pytest.raises(PredicateSandboxError, match="timeout"):
        evaluate_python_predicate("True", (), timeout_seconds=timeout)
