from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import (
    Edge,
    Node,
    OperatorRef,
    Pipeline,
    Port,
    RetryPolicy,
    TaskPolicy,
    Trigger,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_fencing import (
    FencedSqliteSchedulerStore,
    TaskAttemptId,
)
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-12T00:00:00.000000Z")
_T10 = Instant("2026-09-12T00:00:10.000000Z")
_T31 = Instant("2026-09-12T00:00:31.000000Z")
_WS = WorkspaceId("ws-1")


def _workflow(*, retries: int = 1) -> tuple[WorkflowDefinition, Node, Node]:
    source = Node.create(
        operator=OperatorRef("source.table"),
        instance_key="source",
        outputs=(Port("out", "batch"),),
    )
    sink = Node.create(
        operator=OperatorRef("sink.table"),
        instance_key="sink",
        inputs=(Port("in", "batch"),),
    )
    pipeline = Pipeline(
        nodes=(source, sink),
        edges=(Edge(source.id, "out", sink.id, "in"),),
    )
    policies = (
        TaskPolicy(
            source.id,
            retry=RetryPolicy(max_attempts=retries, delay_seconds=0),
        ),
    )
    return WorkflowDefinition(WorkflowId("wf-1"), "Workflow", pipeline, policies), source, sink


def _store(tmp_path: Path, *, retries: int = 1) -> tuple[FencedSqliteSchedulerStore, Node, Node]:
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    store = FencedSqliteSchedulerStore(path, migration_now=_T0)
    workflow, source, sink = _workflow(retries=retries)
    store.put_workflow(_WS, workflow, now=_T0)
    store.create_run(
        _WS,
        WorkflowRunId("wr-1"),
        workflow.id,
        Trigger("manual", "trigger-1"),
        now=_T0,
    )
    return store, source, sink


def test_dependencies_do_not_dispatch_before_predecessor_success(tmp_path: Path) -> None:
    store, source, sink = _store(tmp_path)
    first = store.claim_next_task(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )

    assert first is not None
    assert first.node_id == source.id
    assert (
        store.claim_next_task(
            owner="worker-2",
            lease_token=LeaseToken("lease-2"),
            attempt_id=TaskAttemptId("attempt-2"),
            lease_seconds=30,
            now=_T10,
            workspace_id=_WS,
        )
        is None
    )

    store.complete_task(
        _WS,
        first.attempt_id,
        owner="worker-1",
        lease_token=first.lease_token,
        succeeded=True,
        failure_code=None,
        now=_T10,
    )
    second = store.claim_next_task(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=30,
        now=_T10,
        workspace_id=_WS,
    )

    assert second is not None
    assert second.node_id == sink.id


def test_stale_or_wrong_lease_cannot_heartbeat_or_commit(tmp_path: Path) -> None:
    store, _source, _sink = _store(tmp_path)
    claim = store.claim_next_task(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )
    assert claim is not None

    with pytest.raises(ValueError, match="ownership lost"):
        store.heartbeat_task(
            _WS,
            claim.attempt_id,
            owner="worker-2",
            lease_token=LeaseToken("lease-wrong"),
            lease_seconds=30,
            now=_T10,
        )
    with pytest.raises(ValueError, match="ownership lost"):
        store.complete_task(
            _WS,
            claim.attempt_id,
            owner="worker-1",
            lease_token=LeaseToken("lease-wrong"),
            succeeded=True,
            failure_code=None,
            now=_T10,
        )


def test_expired_attempt_is_reclaimed_and_retried(tmp_path: Path) -> None:
    store, source, _sink = _store(tmp_path, retries=2)
    first = store.claim_next_task(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )
    assert first is not None

    assert store.reclaim_expired(now=_T31) == 1
    second = store.claim_next_task(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=30,
        now=_T31,
        workspace_id=_WS,
    )

    assert second is not None
    assert second.node_id == source.id
    assert second.attempt_ordinal == 2
    with pytest.raises(ValueError, match="ownership lost"):
        store.complete_task(
            _WS,
            first.attempt_id,
            owner="worker-1",
            lease_token=first.lease_token,
            succeeded=True,
            failure_code=None,
            now=_T31,
        )


def test_workflow_succeeds_only_after_all_tasks_commit(tmp_path: Path) -> None:
    store, _source, _sink = _store(tmp_path)
    first = store.claim_next_task(
        owner="worker-1",
        lease_token=LeaseToken("lease-1"),
        attempt_id=TaskAttemptId("attempt-1"),
        lease_seconds=30,
        now=_T0,
        workspace_id=_WS,
    )
    assert first is not None
    store.complete_task(
        _WS,
        first.attempt_id,
        owner=first.lease_owner,
        lease_token=first.lease_token,
        succeeded=True,
        failure_code=None,
        now=_T10,
    )
    assert store.get_run(_WS, WorkflowRunId("wr-1")).state == "running"  # type: ignore[union-attr]
    second = store.claim_next_task(
        owner="worker-2",
        lease_token=LeaseToken("lease-2"),
        attempt_id=TaskAttemptId("attempt-2"),
        lease_seconds=30,
        now=_T10,
        workspace_id=_WS,
    )
    assert second is not None
    store.complete_task(
        _WS,
        second.attempt_id,
        owner=second.lease_owner,
        lease_token=second.lease_token,
        succeeded=True,
        failure_code=None,
        now=_T10,
    )
    assert store.get_run(_WS, WorkflowRunId("wr-1")).state == "succeeded"  # type: ignore[union-attr]
