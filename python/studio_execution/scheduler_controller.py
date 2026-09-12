"""Durable scheduler controller over fenced claims and the execution outbox."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from studio_orchestrator import Instant, LeaseToken
from studio_storage.scheduler_controller import (
    SchedulerControllerStore,
    WorkflowDeploymentConflict,
)
from studio_storage.scheduler_execution import TaskExecutionIntent
from studio_storage.scheduler_fencing import TaskAttemptId

from .scheduler_bridge import plan_scheduler_execution
from .scheduler_dispatch import (
    DurableJobService,
    dispatch_execution_intent,
    reconcile_execution_intent,
)


@dataclass(frozen=True, slots=True)
class SchedulerControllerCycle:
    """Observable result of one bounded controller iteration."""

    published: TaskExecutionIntent | None
    dispatched: int
    reconciled: int


class SchedulerController:
    """Bounded controller logic; daemon timing/leadership are separate concerns."""

    def __init__(self, store: SchedulerControllerStore, service: DurableJobService) -> None:
        self._store = store
        self._service = service

    async def claim_and_publish(
        self,
        *,
        workspace_id: object,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: TaskAttemptId,
        lease_seconds: int,
        now: Instant | str,
    ) -> TaskExecutionIntent | None:
        """Claim one ready task and durably publish its executable intent.

        IDs/tokens are supplied by the outer daemon rather than generated here so
        deterministic tests and future leader protocols can own allocation.
        """

        from studio_storage import WorkspaceId

        if not isinstance(workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        claim = await asyncio.to_thread(
            self._store.claim_next_task,
            owner=owner,
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=lease_seconds,
            now=now,
            workspace_id=workspace_id,
        )
        if claim is None:
            return None

        workflow_run = await asyncio.to_thread(
            self._store.get_run,
            workspace_id,
            claim.workflow_run_id,
        )
        if workflow_run is None:
            await asyncio.to_thread(
                self._store.complete_task,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                succeeded=False,
                failure_code="workflow_run_missing",
                now=now,
            )
            return None

        deployment = await asyncio.to_thread(
            self._store.get_workflow_deployment,
            workspace_id,
            workflow_run.workflow_id,
        )
        if deployment is None:
            await asyncio.to_thread(
                self._store.complete_task,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                succeeded=False,
                failure_code="deployment_missing",
                now=now,
            )
            return None

        try:
            plan = plan_scheduler_execution(
                claim,
                workflow_run,
                str(deployment.project_id),
                now=now,
            )
        except Exception:
            # Unsupported/invalid task definitions are deterministic definition
            # failures. Persist the scheduler failure instead of leaking a live
            # claim until lease expiry.
            await asyncio.to_thread(
                self._store.complete_task,
                workspace_id,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                succeeded=False,
                failure_code="execution_plan_invalid",
                now=now,
            )
            raise

        return await asyncio.to_thread(
            self._store.put_execution_intent,
            workspace_id,
            attempt_id,
            job=plan.job,
            run=plan.run,
            owner=owner,
            lease_token=lease_token,
            now=now,
        )

    async def dispatch_pending(self, *, limit: int = 100) -> int:
        intents = await asyncio.to_thread(self._store.list_execution_intents, limit=limit)
        dispatched = 0
        for intent in intents:
            await dispatch_execution_intent(intent, self._service)
            dispatched += 1
        return dispatched

    async def reconcile_pending(
        self,
        *,
        now: Instant | str,
        limit: int = 100,
    ) -> int:
        intents = await asyncio.to_thread(self._store.list_execution_intents, limit=limit)
        reconciled = 0
        for intent in intents:
            if await reconcile_execution_intent(
                intent,
                self._service,
                self._store,
                now=now,
            ):
                reconciled += 1
        return reconciled

    async def cycle(
        self,
        *,
        workspace_id: object,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: TaskAttemptId,
        lease_seconds: int,
        now: Instant | str,
        outbox_limit: int = 100,
    ) -> SchedulerControllerCycle:
        """Run one bounded publish/dispatch/reconcile iteration."""

        published = await self.claim_and_publish(
            workspace_id=workspace_id,
            owner=owner,
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=lease_seconds,
            now=now,
        )
        dispatched = await self.dispatch_pending(limit=outbox_limit)
        reconciled = await self.reconcile_pending(now=now, limit=outbox_limit)
        return SchedulerControllerCycle(published, dispatched, reconciled)


__all__ = ("SchedulerController", "SchedulerControllerCycle")
