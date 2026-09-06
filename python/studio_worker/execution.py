"""Lease-fenced durable per-cell worker execution and resume composition."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from studio_kernel import (
    CancellationToken,
    CellExecutionResult,
    KernelCellExecutor,
    NotebookExecutionRequest,
    SessionPolicy,
)
from studio_orchestrator import (
    AttemptState,
    CellExecutionIdentity,
    CellResumeRecord,
    ClaimedRun,
    Instant,
    JobState,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
    can_resume_cell,
)
from studio_server import DurableExecutionService
from studio_storage import ArtifactRef, LocalArtifactStore


class WorkerExecutionError(RuntimeError):
    """Raised when a claimed run cannot be executed safely."""


class WorkerLeaseLost(WorkerExecutionError):
    """Raised when heartbeat or a fenced durable mutation loses ownership."""


@dataclass(frozen=True, slots=True)
class WorkerExecutionOutcome:
    state: AttemptState
    executed_cell_ids: tuple[str, ...]
    reused_cell_ids: tuple[str, ...]
    failure_code: str | None = None


def utc_now() -> Instant:
    """Return the canonical UTC instant used at the worker composition boundary."""

    return Instant(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _plus_seconds(value: Instant, seconds: int) -> Instant:
    parsed = datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    return Instant((parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _result_json(result: CellExecutionResult) -> str:
    payload = {
        "cell_id": str(result.cell_id),
        "state": result.state,
        "failure_code": result.failure_code,
        "evidence": [{"kind": ref.kind, "ref": ref.ref} for ref in result.evidence],
        "version": 1,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _artifact_ref(ref: StoredEvidenceRef) -> ArtifactRef | None:
    if ref.digest_algorithm != "sha256" or ref.size_bytes is None or ref.storage_ref is None:
        return None
    return ArtifactRef(
        role=ref.role,
        digest_algorithm=ref.digest_algorithm,
        digest=ref.digest,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        storage_ref=ref.storage_ref,
    )


@dataclass(slots=True)
class DurableWorkerExecution:
    """Execute one already-claimed Run while preserving restart-safe cell checkpoints."""

    service: DurableExecutionService
    artifact_store: LocalArtifactStore
    executor: KernelCellExecutor
    policy: SessionPolicy
    owner: str
    lease_seconds: int = 30
    heartbeat_interval_seconds: float = 5.0
    now: Callable[[], Instant] = utc_now
    _sequence: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.owner or self.owner != self.owner.strip():
            raise ValueError("worker owner must be non-empty and trimmed")
        if self.lease_seconds < 2:
            raise ValueError("lease_seconds must be at least 2")
        if not 0 < self.heartbeat_interval_seconds < self.lease_seconds:
            raise ValueError("heartbeat interval must be positive and shorter than the lease")

    async def _append_event(self, claim: ClaimedRun, kind: str, message: str = "") -> None:
        occurred_at = self.now()
        event = StoredExecutionEvent(
            attempt_id=claim.attempt_id,
            sequence=self._sequence,
            kind=kind,
            message=message,
            occurred_at=occurred_at,
        )
        await self.service.worker_append_events(
            claim.attempt_id,
            (event,),
            owner=self.owner,
            lease_token=claim.lease_token,
            now=occurred_at,
        )
        self._sequence += 1

    async def _verify_resume(
        self,
        identity: CellExecutionIdentity,
        result: StoredCellResult,
        evidence: tuple[StoredEvidenceRef, ...],
    ) -> bool:
        refs = tuple(
            ref
            for ref in evidence
            if ref.cell_id == identity.cell_id and ref.role == "cell-result"
        )
        if not refs:
            return False
        artifact = _artifact_ref(refs[-1])
        if artifact is None:
            return False
        verified = await asyncio.to_thread(self.artifact_store.verify, artifact)
        record = CellResumeRecord(
            run_id=result.run_id,
            cell_id=result.cell_id,
            state=result.state,
            execution_identity_digest=result.execution_identity_digest,
            artifact_digests=(artifact.digest,),
        )
        return can_resume_cell(identity, record, artifacts_verified=verified)

    async def _checkpoint(
        self,
        claim: ClaimedRun,
        identity: CellExecutionIdentity,
        result: CellExecutionResult,
    ) -> None:
        payload = _result_json(result)
        artifact = await asyncio.to_thread(
            self.artifact_store.put_bytes,
            role="cell-result",
            data=payload.encode("utf-8"),
            media_type="application/vnd.ronin.cell-result+json",
        )
        now = self.now()
        await self.service.worker_put_evidence(
            claim.attempt_id,
            StoredEvidenceRef(
                run_id=claim.run.id,
                cell_id=identity.cell_id,
                role=artifact.role,
                digest_algorithm=artifact.digest_algorithm,
                digest=artifact.digest,
                media_type=artifact.media_type,
                size_bytes=artifact.size_bytes,
                storage_ref=artifact.storage_ref,
            ),
            owner=self.owner,
            lease_token=claim.lease_token,
            now=now,
        )
        await self.service.worker_put_cell_result(
            claim.attempt_id,
            StoredCellResult(
                run_id=claim.run.id,
                cell_id=identity.cell_id,
                source_digest=identity.source_digest,
                execution_identity_digest=identity.digest,
                state=result.state,
                result_json=payload,
                updated_at=now,
            ),
            owner=self.owner,
            lease_token=claim.lease_token,
            now=now,
        )

    async def _heartbeat(
        self,
        claim: ClaimedRun,
        cancellation: CancellationToken,
        lease_lost: asyncio.Event,
    ) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval_seconds)
            now = self.now()
            owned = await self.service.worker_heartbeat(
                claim.attempt_id,
                owner=self.owner,
                lease_token=claim.lease_token,
                expires_at=_plus_seconds(now, self.lease_seconds),
                now=now,
            )
            if not owned:
                cancellation.cancel()
                lease_lost.set()
                return

    async def _complete(
        self,
        claim: ClaimedRun,
        state: AttemptState,
        failure_code: str | None,
    ) -> None:
        await self.service.worker_complete_attempt(
            claim.attempt_id,
            state=state,
            failure_code=failure_code,
            owner=self.owner,
            lease_token=claim.lease_token,
            now=self.now(),
        )

    async def run(
        self,
        claim: ClaimedRun,
        request: NotebookExecutionRequest,
        identities: tuple[CellExecutionIdentity, ...],
    ) -> WorkerExecutionOutcome:
        """Execute one claim sequentially, checkpointing before advancing to the next cell."""

        if len(request.cells) != len(identities):
            raise WorkerExecutionError("cell request and identity counts do not match")
        if any(identity.run_id != claim.run.id for identity in identities):
            raise WorkerExecutionError("cell identity run does not match claimed run")
        if str(request.attempt_id) != str(claim.attempt_id):
            raise WorkerExecutionError("kernel request attempt does not match claimed attempt")
        self.policy.validate_isolation(self.executor.isolation)
        self._sequence = 0

        cancellation = CancellationToken()
        lease_lost = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(claim, cancellation, lease_lost))
        executed: list[str] = []
        reused: list[str] = []
        try:
            previous_results = {
                result.cell_id: result
                for result in await self.service.worker_read_cell_results(claim.run.id)
            }
            previous_evidence = await self.service.worker_read_evidence(claim.run.id)
            await self._append_event(claim, "worker.attempt.started")

            for cell, identity in zip(request.cells, identities, strict=True):
                if lease_lost.is_set():
                    raise WorkerLeaseLost("attempt lease lost during execution")

                job = await self.service.status(claim.job.id)
                if job is None:
                    raise WorkerExecutionError("claimed job disappeared from durable store")
                if job.state in {JobState.CANCELLING, JobState.CANCELLED}:
                    cancellation.cancel()
                    await self._append_event(claim, "worker.attempt.cancelled")
                    await self._complete(claim, AttemptState.CANCELLED, None)
                    return WorkerExecutionOutcome(
                        AttemptState.CANCELLED,
                        tuple(executed),
                        tuple(reused),
                    )

                prior = previous_results.get(identity.cell_id)
                if prior is not None and await self._verify_resume(identity, prior, previous_evidence):
                    reused.append(identity.cell_id)
                    await self._append_event(claim, "worker.cell.reused", identity.cell_id)
                    continue

                missing_permissions = self.policy.missing_permissions(cell)
                if missing_permissions:
                    result = CellExecutionResult(
                        cell.cell_id,
                        "failed",
                        "kernel.permission.denied",
                    )
                else:
                    try:
                        result = await self.executor.execute(cell, cancellation)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        result = CellExecutionResult(
                            cell.cell_id,
                            "failed",
                            "kernel.executor.error",
                        )
                if result.cell_id != cell.cell_id:
                    raise WorkerExecutionError("kernel executor changed cell identity")
                if lease_lost.is_set():
                    raise WorkerLeaseLost("attempt lease lost during cell execution")

                await self._checkpoint(claim, identity, result)
                executed.append(identity.cell_id)
                await self._append_event(
                    claim,
                    f"worker.cell.{result.state}",
                    identity.cell_id,
                )
                if result.state == "failed":
                    failure_code = result.failure_code or "kernel.cell.failed"
                    await self._complete(claim, AttemptState.FAILED, failure_code)
                    return WorkerExecutionOutcome(
                        AttemptState.FAILED,
                        tuple(executed),
                        tuple(reused),
                        failure_code,
                    )
                if result.state == "cancelled":
                    await self._complete(claim, AttemptState.CANCELLED, None)
                    return WorkerExecutionOutcome(
                        AttemptState.CANCELLED,
                        tuple(executed),
                        tuple(reused),
                    )

            if lease_lost.is_set():
                raise WorkerLeaseLost("attempt lease lost before completion")
            await self._append_event(claim, "worker.attempt.succeeded")
            await self._complete(claim, AttemptState.SUCCEEDED, None)
            return WorkerExecutionOutcome(
                AttemptState.SUCCEEDED,
                tuple(executed),
                tuple(reused),
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


__all__ = (
    "DurableWorkerExecution",
    "WorkerExecutionError",
    "WorkerExecutionOutcome",
    "WorkerLeaseLost",
    "utc_now",
)