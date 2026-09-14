"""Durable worker variant that delegates only cell execution to a constrained broker."""

from __future__ import annotations

import asyncio

from studio_kernel import ExecutionAttemptId
from studio_orchestrator import AttemptState, CellExecutionIdentity, ClaimedRun
from studio_runners import BrokerContainerKernelExecutor, BrokerExecutorConfig
from studio_storage import LocalArtifactStore

from .execution import DurableWorkerExecution, WorkerExecutionOutcome
from .runtime import LocalWorkerRuntime, LocalWorkerRuntimeConfig


class BrokerWorkerRuntime(LocalWorkerRuntime):
    """Preserve durable worker semantics while removing local Docker authority."""

    def __init__(
        self,
        config: LocalWorkerRuntimeConfig,
        broker: BrokerExecutorConfig,
        **kwargs: object,
    ) -> None:
        if broker.expected_image != config.image:
            raise ValueError("broker runtime image must match worker runtime image")
        self._broker = broker
        super().__init__(config, **kwargs)

    async def _execute_claim(self, claim: ClaimedRun) -> WorkerExecutionOutcome:
        loop = asyncio.get_running_loop()
        try:
            request, identities = await loop.run_in_executor(
                self._preparation_executor,
                self._prepare,
                claim.attempt_id,
                claim.run.id,
                claim.job,
            )
        except Exception:
            await self._service.worker_complete_attempt(
                claim.attempt_id,
                state=AttemptState.FAILED,
                failure_code="worker.preparation.error",
                owner=self.config.owner,
                lease_token=claim.lease_token,
                now=self._now(),
            )
            raise

        executor = BrokerContainerKernelExecutor(
            self._broker,
            ExecutionAttemptId(str(claim.attempt_id)),
        )
        worker = DurableWorkerExecution(
            self._service,
            LocalArtifactStore(self.config.artifact_root),
            executor,
            self._policy,
            self.config.owner,
            lease_seconds=self.config.lease_seconds,
            heartbeat_interval_seconds=self.config.heartbeat_interval_seconds,
            now=self._now,
            artifact_max_workers=self.config.artifact_max_workers,
            artifact_max_in_flight=self.config.artifact_max_in_flight,
        )
        return await worker.run(
            claim,
            request,
            tuple(identity for identity in identities if isinstance(identity, CellExecutionIdentity)),
        )


__all__ = ("BrokerWorkerRuntime",)
