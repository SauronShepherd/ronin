from __future__ import annotations

import sqlite3

import pytest
from studio_core import (
    Node,
    NodeId,
    OperatorRef,
    Pipeline,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    Workspace,
    WorkspaceId,
)
from studio_core.scheduler import WorkflowRunId
from studio_orchestrator import Instant
from studio_storage.scheduler import SqliteSchedulerStore, WorkflowNotFound, WorkflowRunConflict
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = Instant("2026-10-15T00:00:00.000000Z")


class _CommitAcknowledgementLost:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @property
    def in_transaction(self) -> bool:
        return self._connection.in_transaction

    def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        cursor = self._connection.execute(sql, parameters)
        if sql == "COMMIT":
            raise sqlite3.OperationalError("simulated lost commit acknowledgement")
        return cursor

    def close(self) -> None:
        self._connection.close()


def test_scheduler_persists_branch_decisions_idempotently_and_rejects_conflicts(tmp_path) -> None:
    path = tmp_path / "scheduler.sqlite"
    workspace_id = WorkspaceId("branch-workspace")
    workspace_store = SqliteWorkspaceStore(path, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Branch workspace"), now=NOW)
    store = SqliteSchedulerStore(path, migration_now=NOW)
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="branch-gate")
    workflow = WorkflowDefinition(WorkflowId("branch-workflow"), "Branch", Pipeline((node,)))
    store.put_workflow(workspace_id, workflow, now=NOW)
    run_id = WorkflowRunId("branch-run")
    store.create_run(workspace_id, run_id, workflow.id, Trigger("manual", "one"), now=NOW)
    assert store.get_branch_decision(workspace_id, run_id, node.id) is None

    expression = {"op": "equals", "field": "environment", "value": "prod"}
    context = {"environment": "dev"}
    decision = store.apply_branch_decision(
        workspace_id, run_id, node.id, expression, context, now=NOW
    )
    assert not decision.should_run
    assert store.get_branch_decision(workspace_id, run_id, node.id) == decision
    assert (
        store.apply_branch_decision(workspace_id, run_id, node.id, expression, context, now=NOW)
        == decision
    )

    connection = store._connect()
    try:
        version = connection.execute(
            "SELECT row_version FROM task_runs WHERE workspace_id=? AND workflow_run_id=?",
            (str(workspace_id), str(run_id)),
        ).fetchone()["row_version"]
    finally:
        connection.close()
    assert version == 1

    with pytest.raises(WorkflowRunConflict, match="different content"):
        store.apply_branch_decision(
            workspace_id,
            run_id,
            node.id,
            {"op": "equals", "field": "environment", "value": "prod"},
            {"environment": "prod"},
            now=NOW,
        )
    with pytest.raises(WorkflowNotFound, match="does not exist"):
        store.apply_branch_decision(
            workspace_id, run_id, NodeId("missing-node"), expression, context, now=NOW
        )
    assert store.get_branch_decision(workspace_id, WorkflowRunId("missing-run"), node.id) is None


def test_scheduler_rejects_late_branch_decision_without_mutating_terminal_task(tmp_path) -> None:
    path = tmp_path / "scheduler.sqlite"
    workspace_id = WorkspaceId("late-branch-workspace")
    workspace_store = SqliteWorkspaceStore(path, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Late branch"), now=NOW)
    store = SqliteSchedulerStore(path, migration_now=NOW)
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="late-branch-gate")
    workflow = WorkflowDefinition(WorkflowId("late-branch-workflow"), "Late", Pipeline((node,)))
    store.put_workflow(workspace_id, workflow, now=NOW)
    run_id = WorkflowRunId("late-branch-run")
    store.create_run(workspace_id, run_id, workflow.id, Trigger("manual", "late"), now=NOW)

    connection = store._connect()
    try:
        connection.execute(
            "UPDATE task_runs SET state='succeeded' WHERE workspace_id=? AND workflow_run_id=?",
            (str(workspace_id), str(run_id)),
        )
    finally:
        connection.close()

    with pytest.raises(WorkflowRunConflict, match="after task execution has started"):
        store.apply_branch_decision(
            workspace_id,
            run_id,
            node.id,
            {"op": "equals", "field": "environment", "value": "prod"},
            {"environment": "dev"},
            now=NOW,
        )

    task = store.list_task_runs(workspace_id, run_id)[0]
    assert task.state == "succeeded"
    assert store.get_branch_decision(workspace_id, run_id, node.id) is None
    connection = store._connect()
    try:
        version = connection.execute(
            "SELECT row_version FROM task_runs WHERE workspace_id=? AND workflow_run_id=?",
            (str(workspace_id), str(run_id)),
        ).fetchone()["row_version"]
    finally:
        connection.close()
    assert version == 0


def test_branch_decision_survives_lost_commit_acknowledgement(tmp_path, monkeypatch) -> None:
    path = tmp_path / "scheduler.sqlite"
    workspace_id = WorkspaceId("commit-ack-workspace")
    workspace_store = SqliteWorkspaceStore(path, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Commit ack"), now=NOW)
    store = SqliteSchedulerStore(path, migration_now=NOW)
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key="commit-ack-gate")
    workflow = WorkflowDefinition(WorkflowId("commit-ack-workflow"), "Commit", Pipeline((node,)))
    store.put_workflow(workspace_id, workflow, now=NOW)
    run_id = WorkflowRunId("commit-ack-run")
    store.create_run(workspace_id, run_id, workflow.id, Trigger("manual", "commit"), now=NOW)

    connect = store._connect
    monkeypatch.setattr(store, "_connect", lambda: _CommitAcknowledgementLost(connect()))
    expression = {"op": "equals", "field": "environment", "value": "prod"}
    context = {"environment": "prod"}
    with pytest.raises(sqlite3.OperationalError, match="lost commit acknowledgement"):
        store.apply_branch_decision(workspace_id, run_id, node.id, expression, context, now=NOW)

    monkeypatch.setattr(store, "_connect", connect)
    assert store.apply_branch_decision(workspace_id, run_id, node.id, expression, context, now=NOW)
