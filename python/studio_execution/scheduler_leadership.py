"""Leader-fenced bounded scheduler controller execution."""

from __future__ import annotations

import asyncio

from studio_core import WorkspaceId
from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.scheduler_leadership import SchedulerLeaderLease, SchedulerLeadershipStore

from .scheduler_controller import SchedulerController, SchedulerControllerCycle
from .scheduler_dispatch import DurableJobService
from .scheduler_timeout import enforce_task_timeouts


class LeaderFencedSchedulerController(SchedulerController):
    """Scheduler controller whose bounded phases require current durable leadership."""

    def __init__(self, store: SchedulerLeadershipStore, service: DurableJobService) -> None:
        super().__init__(store, service)
        self._leadership_store = store

    async def _assert_leader(
        self,
        lease: SchedulerLeaderLease,
        *,
        now: Instant | str,
    ) -> None:
        await asyncio.to_thread(
            self._leadership_store.assert_scheduler_leadership,
            lease,
            now=now,
        )

    async def cycle_as_leader(
        self,
        lease: SchedulerLeaderLease,
        *,
        workspace_id: WorkspaceId,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: TaskAttemptId,
        lease_seconds: int,
        now: Instant | str,
        outbox_limit: int = 100,
    ) -> SchedulerControllerCycle:
        """Run one bounded controller cycle while repeatedly fencing leader authority."""

        await self._assert_leader(lease, now=now)
        await enforce_task_timeouts(
            self._store,
            self._service,
            now=now,
            limit=outbox_limit,
        )
        await self._assert_leader(lease, now=now)
        published = await self.claim_and_publish(
            workspace_id=workspace_id,
            owner=owner,
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=lease_seconds,
            now=now,
        )
        await self._assert_leader(lease, now=now)
        dispatched = await self.dispatch_pending(now=now, limit=outbox_limit)
        await self._assert_leader(lease, now=now)
        reconciled = await self.reconcile_pending(now=now, limit=outbox_limit)
        await self._assert_leader(lease, now=now)
        return SchedulerControllerCycle(published, dispatched, reconciled)


__all__ = ("LeaderFencedSchedulerController",)
