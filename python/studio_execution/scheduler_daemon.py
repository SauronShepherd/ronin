"""Leader-owning bounded scheduler daemon orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from studio_core import WorkspaceId
from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_backfill import BackfillId
from studio_storage.scheduler_backfill_runtime import SchedulerBackfillRuntimeStore
from studio_storage.scheduler_events import SchedulerEventStore
from studio_storage.scheduler_fencing import TaskAttemptId
from studio_storage.scheduler_leadership import (
    SchedulerLeaderLease,
    SchedulerLeadershipLost,
    SchedulerLeadershipStore,
)
from studio_storage.scheduler_schedule import SchedulerScheduleStore

from .scheduler_backfill import SchedulerBackfillService
from .scheduler_controller import SchedulerControllerCycle
from .scheduler_dispatch import DurableJobService
from .scheduler_event_service import SchedulerEventService
from .scheduler_leadership import LeaderFencedSchedulerController, SchedulerLeadershipGuard
from .scheduler_schedule_service import SchedulerScheduleService

Clock = Callable[[], Instant]
LeaderTokenFactory = Callable[[], LeaseToken]
TaskAttemptFactory = Callable[[], TaskAttemptId]
TaskLeaseTokenFactory = Callable[[], LeaseToken]


@dataclass(frozen=True, slots=True)
class BackfillTarget:
    workspace_id: WorkspaceId
    backfill_id: BackfillId


@dataclass(frozen=True, slots=True)
class SchedulerDaemonWork:
    schedule_workspaces: tuple[WorkspaceId, ...] = ()
    event_workspaces: tuple[WorkspaceId, ...] = ()
    controller_workspaces: tuple[WorkspaceId, ...] = ()
    backfills: tuple[BackfillTarget, ...] = ()


@dataclass(frozen=True, slots=True)
class SchedulerDaemonCycle:
    is_leader: bool
    leader_generation: int | None
    schedule_fires: int = 0
    event_deliveries: int = 0
    backfill_runs: int = 0
    controller_cycles: tuple[SchedulerControllerCycle, ...] = ()


class SchedulerDaemon:
    """Acquire/renew scheduler leadership and run one bounded guarded work cycle."""

    def __init__(
        self,
        *,
        leadership_store: SchedulerLeadershipStore,
        schedule_store: SchedulerScheduleStore,
        event_store: SchedulerEventStore,
        backfill_store: SchedulerBackfillRuntimeStore,
        job_service: DurableJobService,
        owner: str,
        clock: Clock,
        leader_token_factory: LeaderTokenFactory,
        task_attempt_factory: TaskAttemptFactory,
        task_lease_token_factory: TaskLeaseTokenFactory,
        leader_lease_seconds: int = 30,
        task_lease_seconds: int = 30,
    ) -> None:
        if not owner or owner != owner.strip():
            raise ValueError("scheduler daemon owner must be non-empty and trimmed")
        if leader_lease_seconds < 1:
            raise ValueError("leader_lease_seconds must be positive")
        if task_lease_seconds < 1:
            raise ValueError("task_lease_seconds must be positive")
        self._leadership_store = leadership_store
        self._schedule_store = schedule_store
        self._event_store = event_store
        self._backfill_store = backfill_store
        self._job_service = job_service
        self._owner = owner
        self._clock = clock
        self._leader_token_factory = leader_token_factory
        self._task_attempt_factory = task_attempt_factory
        self._task_lease_token_factory = task_lease_token_factory
        self._leader_lease_seconds = leader_lease_seconds
        self._task_lease_seconds = task_lease_seconds
        self._lease: SchedulerLeaderLease | None = None

    @property
    def lease(self) -> SchedulerLeaderLease | None:
        return self._lease

    def _acquire_or_renew(self) -> SchedulerLeaderLease | None:
        now = self._clock()
        if self._lease is not None:
            try:
                self._lease = self._leadership_store.heartbeat_scheduler_leadership(
                    self._lease,
                    lease_seconds=self._leader_lease_seconds,
                    now=now,
                )
                return self._lease
            except SchedulerLeadershipLost:
                self._lease = None
        self._lease = self._leadership_store.acquire_scheduler_leadership(
            owner=self._owner,
            lease_token=self._leader_token_factory(),
            lease_seconds=self._leader_lease_seconds,
            now=now,
        )
        return self._lease

    async def run_once(self, work: SchedulerDaemonWork) -> SchedulerDaemonCycle:
        lease = self._acquire_or_renew()
        if lease is None:
            return SchedulerDaemonCycle(False, None)

        guard = SchedulerLeadershipGuard(self._leadership_store, lease)
        schedule_service = SchedulerScheduleService(
            self._schedule_store,
            authority_check=guard.check,
        )
        event_service = SchedulerEventService(
            self._event_store,
            authority_check=guard.check,
        )
        backfill_service = SchedulerBackfillService(
            self._backfill_store,
            authority_check=guard.check,
        )
        controller = LeaderFencedSchedulerController(
            self._leadership_store,
            self._job_service,
        )

        schedule_fires = 0
        for workspace_id in work.schedule_workspaces:
            now = self._clock()
            result = await schedule_service.tick(
                workspace_id,
                through=now,
                now=now,
            )
            schedule_fires += len(result.fires)

        event_deliveries = 0
        for workspace_id in work.event_workspaces:
            now = self._clock()
            result = await event_service.process_pending(workspace_id, now=now)
            event_deliveries += len(result.delivered)

        backfill_runs = 0
        for target in work.backfills:
            now = self._clock()
            result = await backfill_service.tick(
                target.workspace_id,
                target.backfill_id,
                now=now,
            )
            backfill_runs += len(result.fires)

        controller_cycles: list[SchedulerControllerCycle] = []
        for workspace_id in work.controller_workspaces:
            now = self._clock()
            controller_cycles.append(
                await controller.cycle_as_leader(
                    lease,
                    workspace_id=workspace_id,
                    owner=self._owner,
                    lease_token=self._task_lease_token_factory(),
                    attempt_id=self._task_attempt_factory(),
                    lease_seconds=self._task_lease_seconds,
                    now=now,
                )
            )

        final_now = self._clock()
        durable = self._leadership_store.assert_scheduler_leadership(lease, now=final_now)
        self._lease = durable
        return SchedulerDaemonCycle(
            True,
            durable.generation,
            schedule_fires,
            event_deliveries,
            backfill_runs,
            tuple(controller_cycles),
        )

    def release(self) -> None:
        if self._lease is None:
            return
        lease = self._lease
        self._leadership_store.release_scheduler_leadership(lease, now=self._clock())
        self._lease = None


__all__ = (
    "BackfillTarget",
    "Clock",
    "LeaderTokenFactory",
    "SchedulerDaemon",
    "SchedulerDaemonCycle",
    "SchedulerDaemonWork",
    "TaskAttemptFactory",
    "TaskLeaseTokenFactory",
)
