from __future__ import annotations

import pytest

from studio_execution.branching import UnsupportedBranchExpression, evaluate_branch


def test_branch_composition_is_deterministic_and_explicitly_runs_or_skips() -> None:
    expression = {
        "op": "all",
        "items": [
            {"op": "equals", "field": "environment", "value": "prod"},
            {"op": "not", "items": [{"op": "exists", "field": "paused"}]},
        ],
    }
    assert evaluate_branch(expression, {"environment": "prod"}).should_run
    decision = evaluate_branch(expression, {"environment": "prod", "paused": True})
    assert not decision.should_run
    assert decision.reason == "predicate_false_skip"


def test_branch_evaluation_fails_closed_for_unknown_or_malformed_input() -> None:
    with pytest.raises(UnsupportedBranchExpression):
        evaluate_branch({"op": "python", "source": "True"}, {})
    with pytest.raises(UnsupportedBranchExpression):
        evaluate_branch({"op": "equals", "field": "x", "value": {"nested": True}}, {})
