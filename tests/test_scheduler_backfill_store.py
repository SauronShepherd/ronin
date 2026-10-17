from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from studio_core import (
    Node,
    OperatorRef,
    Pipeline,
    Schedule,
    ScheduleId,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage.scheduler_backfill import (
    BackfillConflict,
    BackfillId,
    BackfillRequest,
    BackfillRun,
    SchedulerBackfillStore,
)
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T00:00:00.000000Z")
_AFTER = Instant("2026-09-13T00:01:00.000000Z")
_WORKSPACE = WorkspaceId("backfill-store-workspace")
_SCHEDULE = ScheduleId("backfill-store-schedule")


def _store(path: Path) -> SchedulerBackfillStore:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WORKSPACE, "Backfill store"), now=_NOW)
    store = SchedulerBackfillStore(path, migration_now=_NOW)
    store.put_workflow(
        _WORKSPACE,
        WorkflowDefinition(
            WorkflowId("backfill-store-workflow"),
            "Example",
            Pipeline((Node.create(operator=OperatorRef("notebook.run"), instance_key="task"),)),
        ),
        now=_NOW,
    )
    store.put_schedule(
        _WORKSPACE,
        Schedule(_SCHEDULE, WorkflowId("backfill-store-workflow"), "* * * * *"),
        now=_NOW,
    )
    return store


def test_backfill_value_objects_reject_invalid_identity_state_and_range() -> None:
    with pytest.raises(ValueError, match="non-empty, trimmed, and single-line"):
        BackfillId("bad\nbackfill")
    with pytest.raises(ValueError, match="at most 256"):
        BackfillId("x" * 257)
    with pytest.raises(ValueError, match="invalid backfill state"):
        BackfillRequest(BackfillId("invalid-state"), _SCHEDULE, _NOW, _AFTER, "unknown")
    with pytest.raises(ValueError, match="aligned to UTC minutes"):
        BackfillRequest(
            BackfillId("unaligned"),
            _SCHEDULE,
            Instant("2026-09-13T00:00:01.000000Z"),
            _AFTER,
        )
    with pytest.raises(ValueError, match="must not precede"):
        BackfillRequest(BackfillId("reversed"), _SCHEDULE, _AFTER, _NOW)
    with pytest.raises(ValueError, match="reserved or created"):
        BackfillRun(_WORKSPACE, BackfillId("bad-run"), _NOW, WorkflowRunId("run-1"), "pending")


def test_backfill_create_is_idempotent_and_rejects_conflicts(tmp_path: Path) -> None:
    store = _store(tmp_path / "backfills.sqlite3")
    request = BackfillRequest(BackfillId("backfill-1"), _SCHEDULE, _NOW, _AFTER)
    assert store.get_backfill(_WORKSPACE, request.id) is None
    assert store.create_backfill(_WORKSPACE, request, now=_NOW) == request
    assert store.create_backfill(_WORKSPACE, request, now=_AFTER) == request
    assert store.get_backfill(_WORKSPACE, request.id) == request
    with pytest.raises(BackfillConflict, match="different content"):
        store.create_backfill(
            _WORKSPACE,
            BackfillRequest(request.id, _SCHEDULE, _NOW, _NOW),
            now=_AFTER,
        )
    with pytest.raises(BackfillConflict, match="schedule does not exist"):
        store.create_backfill(
            _WORKSPACE,
            BackfillRequest(BackfillId("missing-schedule"), ScheduleId("missing"), _NOW, _AFTER),
            now=_NOW,
        )
    with pytest.raises(ValueError, match="start pending"):
        store.create_backfill(_WORKSPACE, replace(request, state="running"), now=_NOW)


def test_backfill_terminal_transitions_are_idempotent_and_conflict_safe(tmp_path: Path) -> None:
    store = _store(tmp_path / "backfill-states.sqlite3")
    cancelled = BackfillRequest(BackfillId("cancelled"), _SCHEDULE, _NOW, _AFTER)
    store.create_backfill(_WORKSPACE, cancelled, now=_NOW)
    expected_cancelled = BackfillRequest(
        cancelled.id, cancelled.schedule_id, cancelled.start_at, cancelled.end_at, "cancelled"
    )
    assert store.cancel_backfill(_WORKSPACE, cancelled.id, now=_AFTER) == expected_cancelled
    assert store.cancel_backfill(_WORKSPACE, cancelled.id, now=_AFTER) == expected_cancelled
    with pytest.raises(BackfillConflict, match="cancelled backfill"):
        store.complete_backfill(_WORKSPACE, cancelled.id, now=_AFTER)

    completed = BackfillRequest(BackfillId("completed"), _SCHEDULE, _NOW, _AFTER)
    store.create_backfill(_WORKSPACE, completed, now=_NOW)
    expected_completed = BackfillRequest(
        completed.id, completed.schedule_id, completed.start_at, completed.end_at, "completed"
    )
    assert store.complete_backfill(_WORKSPACE, completed.id, now=_AFTER) == expected_completed
    assert store.complete_backfill(_WORKSPACE, completed.id, now=_AFTER) == expected_completed
    with pytest.raises(BackfillConflict, match="completed backfill"):
        store.cancel_backfill(_WORKSPACE, completed.id, now=_AFTER)
    with pytest.raises(KeyError):
        store.cancel_backfill(_WORKSPACE, BackfillId("missing"), now=_NOW)


def test_backfill_run_listing_is_empty_and_missing_backfill_errors(tmp_path: Path) -> None:
    store = _store(tmp_path / "backfill-runs.sqlite3")
    backfill = BackfillId("backfill-1")
    store.create_backfill(_WORKSPACE, BackfillRequest(backfill, _SCHEDULE, _NOW, _AFTER), now=_NOW)
    assert store.list_backfill_runs(_WORKSPACE, backfill) == ()
