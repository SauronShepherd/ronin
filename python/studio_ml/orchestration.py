"""Workspace-scoped, lease-fenced ML execution coordination."""

from __future__ import annotations

import asyncio
import hashlib
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from typing import Literal, Protocol, cast
from uuid import uuid4

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.plugins import PluginRouteConflict
from studio_orchestrator import (
    AttemptId,
    AttemptState,
    ClaimedRun,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    StoredCellResult,
)
from studio_orchestrator import (
    RunState as DurableRunState,
)
from studio_storage import ArtifactRef, ArtifactStore

from .domain import Lab, PipelineIR
from .runner import ClusteringResult, ExperimentResult, LocalExperimentRunner
from .services import compile_lab_pipeline

RunState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
MAX_EXECUTION_REQUEST_BYTES = 64 * 1024 * 1024
MAX_INLINE_EXECUTION_REQUEST_BYTES = 1_048_576
EXECUTION_LEASE_SECONDS = 60
EXECUTION_POLL_SECONDS = 0.2


class ExecutionConflict(PluginRouteConflict):
    """An execution ID was reused for a different request in the same workspace."""


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    run_id: str
    state: RunState
    result: ExperimentResult | ClusteringResult | None = None
    error: str | None = None
    result_payload: dict[str, object] | None = None
    workspace_id: str = ""
    lab_id: str = ""
    lab_digest: str = ""
    pipeline_digest: str = ""
    request_digest: str = ""
    lab_json: str | None = None
    pipeline_json: str | None = None
    rows_json: str | None = None
    owner: str | None = None
    lease_expires_at: Instant | None = None
    fence: int = 0
    row_version: int = 0
    attempt_id: str | None = None
    lease_token: str | None = None
    attempt_ordinal: int = 0
    input_error: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"run_id": self.run_id, "state": self.state}
        if self.result is not None:
            payload["result"] = self.result.to_payload()
        elif self.result_payload is not None:
            payload["result"] = self.result_payload
        if self.error is not None:
            payload["error"] = self.error
        return payload


class ExecutionStore(Protocol):
    def create(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot: ...

    def get(self, workspace_id: str, run_id: str) -> ExecutionSnapshot | None: ...

    def list_runnable(self, now: Instant, *, limit: int) -> tuple[ExecutionSnapshot, ...]: ...

    def claim(
        self, workspace_id: str, run_id: str, owner: str, *, now: Instant, lease_until: Instant
    ) -> ExecutionSnapshot | None: ...

    def heartbeat(
        self,
        workspace_id: str,
        run_id: str,
        owner: str,
        fence: int,
        *,
        lease_until: Instant,
    ) -> bool: ...

    def finish(
        self,
        workspace_id: str,
        run_id: str,
        owner: str,
        fence: int,
        *,
        state: Literal["succeeded", "failed"],
        result_payload: dict[str, object] | None = None,
        error: str | None = None,
    ) -> ExecutionSnapshot | None: ...

    def cancel(self, workspace_id: str, run_id: str) -> ExecutionSnapshot: ...


class WorkerPoll(Protocol):
    claim: ClaimedRun | None


class DurableExecutionPort(Protocol):
    """Narrow durable Job service contract consumed by the ML adapter."""

    async def submit(self, job: Job, run: Run) -> Job: ...

    async def status(self, job_id: JobId) -> Job | None: ...

    async def cell_results(self, job_id: JobId) -> tuple[StoredCellResult, ...] | None: ...

    async def worker_poll(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: Instant,
        target: str | None = None,
    ) -> WorkerPoll: ...

    async def worker_heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant,
        now: Instant,
    ) -> bool: ...

    async def worker_put_cell_result(
        self,
        attempt_id: AttemptId,
        result: StoredCellResult,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...

    async def worker_complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        state: AttemptState,
        failure_code: str | None,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> None: ...

    async def cancel(
        self, job_id: JobId, *, now: Instant, fence_active_attempt: bool = False
    ) -> Job: ...


class InMemoryExecutionStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], ExecutionSnapshot] = {}
        self._lock = Lock()

    def create(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
        key = (snapshot.workspace_id, snapshot.run_id)
        with self._lock:
            existing = self._items.get(key)
            if existing is not None:
                if existing.request_digest != snapshot.request_digest:
                    raise ExecutionConflict(f"execution request already exists: {snapshot.run_id}")
                return existing
            self._items[key] = snapshot
            return snapshot

    def get(self, workspace_id: str, run_id: str) -> ExecutionSnapshot | None:
        with self._lock:
            return self._items.get((workspace_id, run_id))

    def list_runnable(self, now: Instant, *, limit: int) -> tuple[ExecutionSnapshot, ...]:
        if limit < 1:
            raise ValueError("runnable execution limit must be positive")
        with self._lock:
            return tuple(
                snapshot
                for snapshot in self._items.values()
                if snapshot.state == "queued"
                or (
                    snapshot.state == "running"
                    and snapshot.lease_expires_at is not None
                    and snapshot.lease_expires_at <= now
                )
            )[:limit]

    def claim(
        self, workspace_id: str, run_id: str, owner: str, *, now: Instant, lease_until: Instant
    ) -> ExecutionSnapshot | None:
        key = (workspace_id, run_id)
        with self._lock:
            current = self._items.get(key)
            if current is None or current.state not in {"queued", "running"}:
                return None
            if (
                current.state == "running"
                and current.lease_expires_at is not None
                and current.lease_expires_at > now
            ):
                return None
            claimed = replace(
                current,
                state="running",
                owner=owner,
                lease_expires_at=lease_until,
                fence=current.fence + 1,
                row_version=current.row_version + 1,
            )
            self._items[key] = claimed
            return claimed

    def heartbeat(
        self,
        workspace_id: str,
        run_id: str,
        owner: str,
        fence: int,
        *,
        lease_until: Instant,
    ) -> bool:
        key = (workspace_id, run_id)
        with self._lock:
            current = self._items.get(key)
            if (
                current is None
                or current.state != "running"
                or current.owner != owner
                or current.fence != fence
            ):
                return False
            self._items[key] = replace(
                current, lease_expires_at=lease_until, row_version=current.row_version + 1
            )
            return True

    def finish(
        self,
        workspace_id: str,
        run_id: str,
        owner: str,
        fence: int,
        *,
        state: Literal["succeeded", "failed"],
        result_payload: dict[str, object] | None = None,
        error: str | None = None,
    ) -> ExecutionSnapshot | None:
        key = (workspace_id, run_id)
        with self._lock:
            current = self._items.get(key)
            if (
                current is None
                or current.state != "running"
                or current.owner != owner
                or current.fence != fence
            ):
                return None
            finished = replace(
                current,
                state=state,
                result_payload=result_payload,
                error=error,
                lab_json=None,
                rows_json=None,
                owner=None,
                lease_expires_at=None,
                row_version=current.row_version + 1,
            )
            self._items[key] = finished
            return finished

    def cancel(self, workspace_id: str, run_id: str) -> ExecutionSnapshot:
        key = (workspace_id, run_id)
        with self._lock:
            current = self._items.get(key)
            if current is None:
                raise KeyError(run_id)
            if current.state in {"queued", "running"}:
                current = replace(
                    current,
                    state="cancelled",
                    lab_json=None,
                    rows_json=None,
                    owner=None,
                    lease_expires_at=None,
                    fence=current.fence + 1,
                    row_version=current.row_version + 1,
                )
                self._items[key] = current
            return current


class JobStoreExecutionStore:
    """ML request adapter over the canonical durable Job/Run/Attempt store."""

    target = "ml-studio.execute"

    def __init__(
        self, service: DurableExecutionPort, artifact_store: ArtifactStore | None = None
    ) -> None:
        self._service = service
        self._artifact_store = artifact_store

    @staticmethod
    def _ids(workspace_id: str, run_id: str) -> tuple[JobId, RunId]:
        identity = hashlib.sha256(f"{workspace_id}\0{run_id}".encode()).hexdigest()
        return JobId(f"ml-{identity}"), RunId(f"ml-{identity}")

    @staticmethod
    def _parameters(job: Job) -> dict[str, object]:
        value = decode_canonical_json(job.parameters_json)
        if not isinstance(value, dict):
            raise ValueError("stored ML job parameters must be an object")
        return cast(dict[str, object], value)

    def create(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
        job_id, durable_run_id = self._ids(snapshot.workspace_id, snapshot.run_id)
        now = _now()
        rows_json = snapshot.rows_json
        rows_artifact: dict[str, object] | None = None
        lab_size = len((snapshot.lab_json or "").encode("utf-8"))
        pipeline_size = len((snapshot.pipeline_json or "").encode("utf-8"))
        rows_size = len(rows_json.encode("utf-8")) if rows_json is not None else 0
        if lab_size + pipeline_size + rows_size + 256 > MAX_EXECUTION_REQUEST_BYTES:
            raise ValueError(f"ML execution request exceeds {MAX_EXECUTION_REQUEST_BYTES} bytes")
        if (
            rows_json is not None
            and lab_size + pipeline_size + rows_size + 1024 > MAX_INLINE_EXECUTION_REQUEST_BYTES
        ):
            if self._artifact_store is None:
                raise ValueError("artifact store is required for large async ML execution inputs")
            artifact = self._artifact_store.put_bytes(
                role="ml-execution-input",
                data=rows_json.encode("utf-8"),
                media_type="application/json",
            )
            rows_artifact = {
                "role": artifact.role,
                "digest_algorithm": artifact.digest_algorithm,
                "digest": artifact.digest,
                "media_type": artifact.media_type,
                "size_bytes": artifact.size_bytes,
                "storage_ref": artifact.storage_ref,
            }
            rows_json = None
        parameters = {
            "schema": "ronin.ml-execution.v1",
            "workspace_id": snapshot.workspace_id,
            "run_id": snapshot.run_id,
            "lab_id": snapshot.lab_id,
            "lab_digest": snapshot.lab_digest,
            "pipeline_digest": snapshot.pipeline_digest,
            "request_digest": snapshot.request_digest,
            "lab_json": snapshot.lab_json,
            "pipeline_json": snapshot.pipeline_json,
            "rows_json": rows_json,
            "rows_artifact": rows_artifact,
        }
        job = Job(
            id=job_id,
            project_id=snapshot.workspace_id,
            idempotency_key=f"ml:{job_id.value.removeprefix('ml-')}",
            request_digest=snapshot.request_digest,
            state=JobState.QUEUED,
            created_at=now,
            updated_at=now,
            target=self.target,
            parameters_json=encode_canonical_json(parameters).decode("utf-8"),
        )
        run = Run(
            id=durable_run_id,
            job_id=job_id,
            ordinal=1,
            state=DurableRunState.PENDING,
            not_before=now,
            created_at=now,
            updated_at=now,
        )
        try:
            created = asyncio.run(self._service.submit(job, run))
        except ValueError as exc:
            raise ExecutionConflict(f"execution request already exists: {snapshot.run_id}") from exc
        if (
            created.request_digest != snapshot.request_digest
            or created.project_id != snapshot.workspace_id
        ):
            raise ExecutionConflict(f"execution request already exists: {snapshot.run_id}")
        return self.get(snapshot.workspace_id, snapshot.run_id) or snapshot

    def get(self, workspace_id: str, run_id: str) -> ExecutionSnapshot | None:
        job_id, durable_run_id = self._ids(workspace_id, run_id)
        job = asyncio.run(self._service.status(job_id))
        if job is None:
            return None
        parameters = self._parameters(job)
        if (
            job.target != self.target
            or job.project_id != workspace_id
            or parameters.get("workspace_id") != workspace_id
            or parameters.get("run_id") != run_id
        ):
            return None
        state: RunState = cast(
            RunState,
            "queued"
            if job.state is JobState.QUEUED
            else "running"
            if job.state in {JobState.RUNNING, JobState.CANCELLING}
            else job.state.value,
        )
        result_payload = None
        error = job.failure_code
        if job.state in {JobState.SUCCEEDED, JobState.FAILED}:
            cells = asyncio.run(self._service.cell_results(job_id)) or ()
            for cell in cells:
                expected_digest = str(parameters.get("request_digest", ""))
                if cell.cell_id == "ml-result" and cell.execution_identity_digest == str(
                    expected_digest
                ):
                    decoded = decode_canonical_json(cell.result_json)
                    if isinstance(decoded, dict):
                        if cell.state == "failed":
                            saved_error = decoded.get("error")
                            if isinstance(saved_error, str):
                                error = saved_error
                        elif cell.state == "succeeded":
                            result_payload = cast(dict[str, object], decoded)
        return ExecutionSnapshot(
            run_id=run_id,
            state=state,
            error=error,
            result_payload=result_payload,
            workspace_id=workspace_id,
            lab_id=str(parameters.get("lab_id", "")),
            lab_digest=str(parameters.get("lab_digest", "")),
            pipeline_digest=str(parameters.get("pipeline_digest", "")),
            request_digest=str(parameters.get("request_digest", job.request_digest)),
            lab_json=cast(str | None, parameters.get("lab_json"))
            if state in {"queued", "running"}
            else None,
            pipeline_json=cast(str | None, parameters.get("pipeline_json"))
            if state in {"queued", "running"}
            else None,
            rows_json=cast(str | None, parameters.get("rows_json"))
            if state in {"queued", "running"}
            else None,
        )

    def claim_next(self, owner: str) -> ExecutionSnapshot | None:
        result = asyncio.run(
            self._service.worker_poll(
                owner=owner,
                lease_token=LeaseToken(str(uuid4())),
                attempt_id=AttemptId(str(uuid4())),
                lease_seconds=EXECUTION_LEASE_SECONDS,
                now=_now(),
                target=self.target,
            )
        )
        claim = result.claim
        if claim is None:
            return None
        parameters = self._parameters(claim.job)
        input_error = None
        rows_json = cast(str | None, parameters.get("rows_json"))
        if rows_json is None and parameters.get("rows_artifact") is not None:
            try:
                rows_json = self._load_rows_artifact(parameters["rows_artifact"])
            except Exception:
                input_error = "stored ML execution input artifact could not be verified"
        return ExecutionSnapshot(
            run_id=str(parameters["run_id"]),
            state="running",
            workspace_id=claim.job.project_id,
            lab_id=str(parameters["lab_id"]),
            lab_digest=str(parameters["lab_digest"]),
            pipeline_digest=str(parameters.get("pipeline_digest", "")),
            request_digest=str(parameters["request_digest"]),
            lab_json=cast(str | None, parameters.get("lab_json")),
            pipeline_json=cast(str | None, parameters.get("pipeline_json")),
            rows_json=rows_json,
            owner=owner,
            lease_expires_at=_lease_until(_now()),
            attempt_id=str(claim.attempt_id),
            lease_token=str(claim.lease_token),
            attempt_ordinal=claim.attempt_ordinal,
            input_error=input_error,
        )

    def _load_rows_artifact(self, value: object) -> str:
        if self._artifact_store is None or not isinstance(value, dict):
            raise ValueError("stored ML execution input artifact is unavailable")
        fields = {
            "role",
            "digest_algorithm",
            "digest",
            "media_type",
            "size_bytes",
            "storage_ref",
        }
        if set(value) != fields:
            raise ValueError("stored ML execution input artifact reference is invalid")
        if (
            not isinstance(value["role"], str)
            or not isinstance(value["digest_algorithm"], str)
            or not isinstance(value["digest"], str)
            or (value["media_type"] is not None and not isinstance(value["media_type"], str))
            or not isinstance(value["size_bytes"], int)
            or isinstance(value["size_bytes"], bool)
            or not isinstance(value["storage_ref"], str)
        ):
            raise ValueError("stored ML execution input artifact reference is invalid")
        ref = ArtifactRef(
            role=value["role"],
            digest_algorithm=value["digest_algorithm"],
            digest=value["digest"],
            media_type=cast(str | None, value["media_type"]),
            size_bytes=value["size_bytes"],
            storage_ref=value["storage_ref"],
        )
        if ref.role != "ml-execution-input" or ref.media_type != "application/json":
            raise ValueError("stored ML execution input artifact metadata is invalid")
        if ref.digest_algorithm != "sha256" or ref.size_bytes > MAX_EXECUTION_REQUEST_BYTES:
            raise ValueError("stored ML execution input artifact exceeds supported bounds")
        if not self._artifact_store.verify(ref):
            raise ValueError("stored ML execution input artifact failed verification")
        data = self._artifact_store.get_bytes(ref)
        if (
            len(data) != ref.size_bytes
            or len(data) > MAX_EXECUTION_REQUEST_BYTES
            or hashlib.sha256(data).hexdigest() != ref.digest
        ):
            raise ValueError("stored ML execution input artifact integrity check failed")
        return data.decode("utf-8", errors="strict")

    def heartbeat_claim(self, snapshot: ExecutionSnapshot) -> bool:
        if snapshot.attempt_id is None or snapshot.lease_token is None or snapshot.owner is None:
            return False
        now = _now()
        return asyncio.run(
            self._service.worker_heartbeat(
                AttemptId(snapshot.attempt_id),
                owner=snapshot.owner,
                lease_token=LeaseToken(snapshot.lease_token),
                expires_at=_lease_until(now),
                now=now,
            )
        )

    def finish_claim(
        self,
        snapshot: ExecutionSnapshot,
        *,
        state: Literal["succeeded", "failed"],
        result_payload: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        if snapshot.attempt_id is None or snapshot.lease_token is None or snapshot.owner is None:
            raise ValueError("durable ML claim is missing its lease identity")
        attempt_id = AttemptId(snapshot.attempt_id)
        lease_token = LeaseToken(snapshot.lease_token)
        now = _now()
        if (state == "succeeded" and result_payload is not None) or (
            state == "failed" and error is not None
        ):
            job_id, run_id = self._ids(snapshot.workspace_id, snapshot.run_id)
            del job_id
            payload = result_payload if state == "succeeded" else {"error": error}
            asyncio.run(
                self._service.worker_put_cell_result(
                    attempt_id,
                    StoredCellResult(
                        run_id=run_id,
                        cell_id="ml-result",
                        source_digest=snapshot.lab_digest,
                        execution_identity_digest=snapshot.request_digest,
                        state=state,
                        result_json=encode_canonical_json(payload).decode("utf-8"),
                        updated_at=now,
                    ),
                    owner=snapshot.owner,
                    lease_token=lease_token,
                    now=now,
                )
            )
        asyncio.run(
            self._service.worker_complete_attempt(
                attempt_id,
                state=AttemptState.SUCCEEDED if state == "succeeded" else AttemptState.FAILED,
                failure_code=None if error is None else "ml_execution_failed",
                owner=snapshot.owner,
                lease_token=lease_token,
                now=_now(),
            )
        )

    def cancel(self, workspace_id: str, run_id: str) -> ExecutionSnapshot:
        job_id, _ = self._ids(workspace_id, run_id)
        job = asyncio.run(self._service.cancel(job_id, now=_now(), fence_active_attempt=True))
        if job.project_id != workspace_id or job.target != self.target:
            raise KeyError(run_id)
        snapshot = self.get(workspace_id, run_id)
        if snapshot is None:
            raise KeyError(run_id)
        return replace(snapshot, state="cancelled", lab_json=None, rows_json=None)


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _lease_until(now: Instant) -> Instant:
    parsed = datetime.strptime(str(now), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    lease = parsed + timedelta(seconds=EXECUTION_LEASE_SECONDS)
    return Instant(lease.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


class LocalExecutionCoordinator:
    """Bounded coordinator that recovers stored requests under expiring owner fences."""

    def __init__(
        self,
        runner: LocalExperimentRunner | None = None,
        max_workers: int = 2,
        store: ExecutionStore | JobStoreExecutionStore | None = None,
        autostart: bool = True,
    ) -> None:
        if max_workers < 1 or max_workers > 32:
            raise ValueError("max_workers must be between 1 and 32")
        self._runner = runner or LocalExperimentRunner()
        self._store = store or InMemoryExecutionStore()
        self._owner = str(uuid4())
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ronin-ml")
        self._max_workers = max_workers
        self._lock = Lock()
        self._admission_lock = Lock()
        self._owned: dict[tuple[str, str], int] = {}
        self._claims: dict[tuple[str, str], ExecutionSnapshot] = {}
        self._active: set[tuple[str, str]] = set()
        self._futures: dict[tuple[str, str], Future[object]] = {}
        self._stop = Event()
        self._closing = Event()
        self._started = False
        self._poller = Thread(target=self._poll, name="ronin-ml-coordinator", daemon=True)
        if autostart:
            self.start()

    def start(self) -> None:
        """Start bounded polling after the owning plugin has entered service."""
        if self._closing.is_set():
            raise RuntimeError("execution coordinator is closed")
        if self._started:
            return
        self._started = True
        self._poller.start()

    def submit(
        self,
        workspace_id: str,
        run_id: str,
        lab: Lab,
        rows: list[dict[str, object]],
        pipeline: PipelineIR | None = None,
    ) -> ExecutionSnapshot:
        pipeline = pipeline or compile_lab_pipeline(lab)
        if dict(pipeline.parameters).get("lab_digest") != lab.digest:
            raise ValueError("compiled ML pipeline is not bound to the submitted Lab")
        lab_json = lab.to_json()
        pipeline_json = pipeline.to_json()
        rows_json = encode_canonical_json(rows).decode("utf-8")
        request_body = encode_canonical_json(
            {"lab": lab.to_payload(), "pipeline": pipeline.to_payload(), "rows": rows}
        )
        if len(request_body) > MAX_EXECUTION_REQUEST_BYTES:
            raise ValueError(f"ML execution request exceeds {MAX_EXECUTION_REQUEST_BYTES} bytes")
        request_digest = hashlib.sha256(request_body).hexdigest()
        snapshot = ExecutionSnapshot(
            run_id=run_id,
            state="queued",
            workspace_id=workspace_id,
            lab_id=lab.id,
            lab_digest=lab.digest,
            pipeline_digest=pipeline.digest,
            request_digest=request_digest,
            lab_json=lab_json,
            pipeline_json=pipeline_json,
            rows_json=rows_json,
        )
        return self._store.create(snapshot)

    def _poll(self) -> None:
        while not self._stop.is_set():
            now = _now()
            if isinstance(self._store, JobStoreExecutionStore):
                with self._lock:
                    claims = tuple(self._claims.items())
                for key, claim in claims:
                    if not self._store.heartbeat_claim(claim):
                        with self._lock:
                            self._claims.pop(key, None)
                            self._owned.pop(key, None)
                with self._admission_lock:
                    with self._lock:
                        capacity = self._max_workers - len(self._active)
                    while not self._closing.is_set() and capacity > 0:
                        claimed = self._store.claim_next(self._owner)
                        if claimed is None:
                            break
                        key = (claimed.workspace_id, claimed.run_id)
                        with self._lock:
                            self._active.add(key)
                            self._claims[key] = claimed
                            self._owned[key] = claimed.attempt_ordinal
                            future = self._executor.submit(self._execute, claimed)
                            self._futures[key] = future
                        future.add_done_callback(self._forget_future)
                        capacity -= 1
                self._stop.wait(EXECUTION_POLL_SECONDS)
                continue
            with self._lock:
                owned = tuple(self._owned.items())
            for (workspace_id, run_id), fence in owned:
                if not self._store.heartbeat(
                    workspace_id,
                    run_id,
                    self._owner,
                    fence,
                    lease_until=_lease_until(now),
                ):
                    with self._lock:
                        self._owned.pop((workspace_id, run_id), None)
            with self._admission_lock:
                with self._lock:
                    capacity = self._max_workers - len(self._active)
                if not self._closing.is_set() and capacity > 0:
                    for snapshot in self._store.list_runnable(now, limit=capacity):
                        key = (snapshot.workspace_id, snapshot.run_id)
                        with self._lock:
                            if self._closing.is_set() or len(self._active) >= self._max_workers:
                                break
                            self._active.add(key)
                        claimed = self._store.claim(
                            snapshot.workspace_id,
                            snapshot.run_id,
                            self._owner,
                            now=now,
                            lease_until=_lease_until(now),
                        )
                        if claimed is None:
                            with self._lock:
                                self._active.discard(key)
                            continue
                        with self._lock:
                            self._owned[key] = claimed.fence
                            future = self._executor.submit(self._execute, claimed)
                            self._futures[key] = future
                        future.add_done_callback(self._forget_future)
            self._stop.wait(EXECUTION_POLL_SECONDS)

    def _forget_future(self, future: Future[object]) -> None:
        with self._lock:
            for key, tracked in tuple(self._futures.items()):
                if tracked is future:
                    self._futures.pop(key, None)
                    self._active.discard(key)
                    self._claims.pop(key, None)

    def _execute(self, claimed: ExecutionSnapshot) -> object:
        key = (claimed.workspace_id, claimed.run_id)
        try:
            if isinstance(self._store, JobStoreExecutionStore):
                with self._lock:
                    owned = self._claims.get(key)
                if owned is None or owned.attempt_id != claimed.attempt_id:
                    return None
            else:
                current = self._store.get(claimed.workspace_id, claimed.run_id)
                if (
                    current is None
                    or current.state != "running"
                    or current.owner != self._owner
                    or current.fence != claimed.fence
                ):
                    return None
            if claimed.input_error is not None:
                raise ValueError(claimed.input_error)
            if claimed.lab_json is None or claimed.rows_json is None:
                raise ValueError("execution request is missing its recoverable input snapshot")
            lab = Lab.from_json(claimed.lab_json)
            pipeline = (
                PipelineIR.from_json(claimed.pipeline_json)
                if claimed.pipeline_json is not None
                else None
            )
            rows = decode_canonical_json(claimed.rows_json)
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise ValueError("stored execution rows must be an array of objects")
            execution_rows = cast(list[dict[str, object]], rows)
            request_payload: dict[str, object] = {"lab": lab.to_payload(), "rows": execution_rows}
            if pipeline is not None:
                request_payload["pipeline"] = pipeline.to_payload()
            request_body = encode_canonical_json(request_payload)
            if lab.digest != claimed.lab_digest:
                raise ValueError("stored execution Lab digest does not match its input snapshot")
            if pipeline is not None and (
                pipeline.digest != claimed.pipeline_digest
                or dict(pipeline.parameters).get("lab_digest") != lab.digest
            ):
                raise ValueError("stored execution pipeline digest does not match its Lab snapshot")
            if (
                len(request_body) > MAX_EXECUTION_REQUEST_BYTES
                or hashlib.sha256(request_body).hexdigest() != claimed.request_digest
            ):
                raise ValueError(
                    "stored execution request digest does not match its input snapshot"
                )
            result: ExperimentResult | ClusteringResult
            if lab.task == "clustering":
                result = self._runner.run_clustering_result(lab, execution_rows)
            else:
                result = self._runner.run(lab, execution_rows)
            if isinstance(self._store, JobStoreExecutionStore):
                self._store.finish_claim(
                    claimed, state="succeeded", result_payload=result.to_payload()
                )
                return result
            finished = self._store.finish(
                claimed.workspace_id,
                claimed.run_id,
                self._owner,
                claimed.fence,
                state="succeeded",
                result_payload=result.to_payload(),
            )
            return result if finished is not None else None
        except Exception as exc:
            if isinstance(self._store, JobStoreExecutionStore):
                with suppress(Exception):
                    self._store.finish_claim(claimed, state="failed", error=str(exc))
            else:
                self._store.finish(
                    claimed.workspace_id,
                    claimed.run_id,
                    self._owner,
                    claimed.fence,
                    state="failed",
                    error=str(exc),
                )
            raise
        finally:
            with self._lock:
                self._owned.pop(key, None)
                self._claims.pop(key, None)

    def status(self, workspace_id: str, run_id: str) -> ExecutionSnapshot:
        snapshot = self._store.get(workspace_id, run_id)
        if snapshot is None:
            raise KeyError(run_id)
        return snapshot

    def cancel(self, workspace_id: str, run_id: str) -> ExecutionSnapshot:
        snapshot = self._store.cancel(workspace_id, run_id)
        with self._lock:
            self._owned.pop((workspace_id, run_id), None)
        return snapshot

    def close(self) -> None:
        self._closing.set()
        with self._admission_lock:
            pass
        self._executor.shutdown(wait=True, cancel_futures=False)
        self._stop.set()
        if self._started:
            self._poller.join(timeout=5)


__all__ = [
    "ExecutionConflict",
    "ExecutionSnapshot",
    "ExecutionStore",
    "InMemoryExecutionStore",
    "JobStoreExecutionStore",
    "DurableExecutionPort",
    "LocalExecutionCoordinator",
    "MAX_EXECUTION_REQUEST_BYTES",
    "MAX_INLINE_EXECUTION_REQUEST_BYTES",
    "RunState",
]
