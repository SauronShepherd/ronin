import pytest
from studio_execution import (
    BranchDecisionStore,
    BranchStateConflict,
    SqliteBranchDecisionStore,
)
from studio_execution.branching import BranchDecision


def test_branch_decision_store_is_idempotent_and_restart_stable() -> None:
    store = BranchDecisionStore()
    first = store.record(
        "workflow",
        3,
        "gate",
        7,
        BranchDecision(False, "predicate_false_skip"),
        ("task-b", "task-a"),
    )
    replay = store.record(
        "workflow",
        3,
        "gate",
        7,
        BranchDecision(False, "predicate_false_skip"),
        ("task-a", "task-b"),
    )
    assert replay == first
    assert replay.skipped_tasks == ("task-a", "task-b")


def test_branch_decision_store_rejects_changed_decision_for_same_snapshot() -> None:
    store = BranchDecisionStore()
    store.record("workflow", 3, "gate", 7, BranchDecision(True, "predicate_true"))
    with pytest.raises(BranchStateConflict, match="conflicts"):
        store.record("workflow", 3, "gate", 7, BranchDecision(False, "predicate_false_skip"))


def test_sqlite_branch_decision_store_survives_reopen_and_rejects_conflicts(tmp_path) -> None:
    path = tmp_path / "scheduler.sqlite"
    decision = BranchDecision(False, "predicate_false_skip")
    first = SqliteBranchDecisionStore(path)
    assert first.record("workflow", 3, "gate", 7, decision, ("task-a",))

    reopened = SqliteBranchDecisionStore(path)
    assert reopened.get("workflow", 3, "gate").skipped_tasks == ("task-a",)
    assert reopened.record("workflow", 3, "gate", 7, decision, ("task-a",)).decision == decision
    with pytest.raises(BranchStateConflict):
        reopened.record("workflow", 3, "gate", 7, BranchDecision(True, "predicate_true"))
