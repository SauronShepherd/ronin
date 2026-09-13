from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from studio_core import Workspace, WorkspaceId
from studio_execution import DurableExecutionService
from studio_execution.scheduler_leadership import LeaderFencedSchedulerController
from studio_orchestrator import Instant, LeaseToken
from studio_storage import InMemoryJobStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.scheduler_leadership import (
    SchedulerLeadershipLost,
    SchedulerLeadershipStore,
)
from studio_storage.workspaces import SqliteWorkspaceStore

_T0 = Instant("2026-09-13T08:30:00.000000Z")
_T10 = Instant("2026-09-13T08:30:10.000000Z")
_T31 = Instant("2026-09-13T08:30:31.000000Z")
_WS = WorkspaceId("workspace-1")


def _store(tmp_path: Path) -> SchedulerLeadershipStore:
    path = tmp_path / "ronin.sqlite3"
    workspaces = SqliteWorkspaceStore(path, migration_now=_T0)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    return SchedulerLeadershipStore(path, migration_now=_T0)


def test_scheduler_leadership_is_exclusive_and_heartbeat_preserves_generation(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    first = store.acquire_scheduler_leadership(
        owner="scheduler-a",
        lease_token=LeaseToken("leader-a"),
        lease_seconds=30,
        now=_T0,
    )
    assert first is not None
    assert first.generation == 1

    blocked = store.acquire_scheduler_leadership(
        owner="scheduler-b",
        lease_token=LeaseToken("leader-b"),
        lease_seconds=30,
        now=_T10,
    )
    assert blocked is None

    renewed = store.heartbeat_scheduler_leadership(first, lease_seconds=30, now=_T10)
    assert renewed.generation == first.generation
    assert renewed.lease_expires_at > first.lease_expires_at
    assert store.assert_scheduler_leadership(renewed, now=_T10) == renewed


def test_scheduler_leadership_takeover_increments_generation_and_fences_stale_owner(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    first = store.acquire_scheduler_leadership(
        owner="scheduler-a",
        lease_token=LeaseToken("leader-a"),
        lease_seconds=30,
        now=_T0,
    )
    assert first is not None

    second = store.acquire_scheduler_leadership(
        owner="scheduler-b",
        lease_token=LeaseToken("leader-b"),
        lease_seconds=30,
        now=_T31,
    )
    assert second is not None
    assert second.generation == first.generation + 1

    with pytest.raises(SchedulerLeadershipLost, match="leadership lost"):
        store.assert_scheduler_leadership(first, now=_T31)
    with pytest.raises(SchedulerLeadershipLost, match="leadership lost"):
        store.heartbeat_scheduler_leadership(first, lease_seconds=30, now=_T31)


def test_release_retains_generation_for_next_leader(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.acquire_scheduler_leadership(
        owner="scheduler-a",
        lease_token=LeaseToken("leader-a"),
        lease_seconds=30,
        now=_T0,
    )
    assert first is not None
    store.release_scheduler_leadership(first, now=_T10)

    second = store.acquire_scheduler_leadership(
        owner="scheduler-b",
        lease_token=LeaseToken("leader-b"),
        lease_seconds=30,
        now=_T10,
    )
    assert second is not None
    assert second.generation == 2

    with pytest.raises(SchedulerLeadershipLost):
        store.assert_scheduler_leadership(first, now=_T10)


def test_leader_fenced_controller_rejects_stale_lease_before_cycle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    lease = store.acquire_scheduler_leadership(
        owner="scheduler-a",
        lease_token=LeaseToken("leader-a"),
        lease_seconds=30,
        now=_T0,
    )
    assert lease is not None
    store.release_scheduler_leadership(lease, now=_T10)

    async def scenario() -> None:
        service = DurableExecutionService(InMemoryJobStore())
        try:
            controller = LeaderFencedSchedulerController(store, service)
            with pytest.raises(SchedulerLeadershipLost):
                await controller.cycle_as_leader(
                    lease,
                    workspace_id=_WS,
                    owner="controller-a",
                    lease_token=LeaseToken("task-lease"),
                    attempt_id=TaskAttemptId("attempt-1"),
                    lease_seconds=30,
                    now=_T10,
                )
        finally:
            await service.aclose()

    asyncio.run(scenario())
