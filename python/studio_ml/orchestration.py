"""Workspace-scoped, lease-fenced ML execution coordination."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext, suppress
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
from studio_storage.ports import ArtifactReferenceBarrier
from studio_kernel import CancellationToken

from .domain import Lab, PipelineIR
from .runner import (
    ClusteringResult,
    ExperimentResult,
    LocalExperimentRunner,
    MLExecutionCancelled,
)
from .services import compile_lab_pipeline

RunState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
MAX_EXECUTION_REQUEST_BYTES = 64 * 1024 * 1024
MAX_INLINE_EXECUTION_REQUEST_BYTES = 1_048_576
MAX_INLINE_NODE_CHECKPOINT_BYTES = 262_144
MAX_NODE_CHECKPOINT_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_PLUGIN_STAGE_ARTIFACT_BYTES = 512 * 1024
MAX_MATERIALIZED_MODEL_BYTES = 64 * 1024 * 1024
EXECUTION_LEASE_SECONDS = 60
EXECUTION_POLL_SECONDS = 0.2


def _retry_invalidated_node_ids(pipeline: PipelineIR, from_stage: str) -> set[str]:
    """Resolve a stage kind or ``node:<id>`` selector and its descendants."""
    ordered_nodes = pipeline.execution_order()
    if from_stage.startswith("node:"):
        requested_id = from_stage[len("node:") :]
        roots = {node.id for node in ordered_nodes if node.id == requested_id}
    else:
        roots = {node.id for node in ordered_nodes if node.kind == from_stage}
        if not roots:
            roots = {node.id for node in ordered_nodes if node.id == from_stage}
    if not roots:
        return set()
    invalidated = set(roots)
    while True:
        descendants = {
            node.id
            for node in ordered_nodes
            if node.id not in invalidated
            and set(pipeline.dependency_ids(node)) & invalidated
        }
        if not descendants:
            return invalidated
        invalidated.update(descendants)


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
    node_checkpoints: dict[str, object] | None = None
    retry_of_run_id: str | None = None
    retry_from_stage: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"run_id": self.run_id, "state": self.state}
        if self.pipeline_json is not None:
            try:
                pipeline = PipelineIR.from_json(self.pipeline_json)
            except (TypeError, ValueError):
                pipeline = None
            if pipeline is not None:
                payload["pipeline_stages"] = [
                    {"id": node.id, "kind": node.kind} for node in pipeline.nodes
                ]
        if self.result is not None:
            payload["result"] = self.result.to_payload()
        elif self.result_payload is not None:
            payload["result"] = self.result_payload
        if self.error is not None:
            payload["error"] = self.error
        if self.retry_of_run_id is not None:
            payload["retry_of_run_id"] = self.retry_of_run_id
        if self.retry_from_stage is not None:
            payload["retry_from_stage"] = self.retry_from_stage
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
                pipeline_json=None,
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
                    pipeline_json=None,
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
        self,
        service: DurableExecutionPort,
        artifact_store: ArtifactStore | None = None,
        *,
        artifact_reference_barrier: ArtifactReferenceBarrier | None = None,
    ) -> None:
        self._service = service
        self._artifact_store = artifact_store
        self._artifact_reference_barrier = artifact_reference_barrier

    def _writer_lease(self) -> AbstractContextManager[None]:
        if self._artifact_reference_barrier is None:
            return nullcontext()
        return self._artifact_reference_barrier.writer()

    @staticmethod
    def _ids(workspace_id: str, run_id: str) -> tuple[JobId, RunId]:
        identity = hashlib.sha256(f"{workspace_id}\0{run_id}".encode()).hexdigest()
        return JobId(f"ml-{identity}"), RunId(f"ml-{identity}")

    @staticmethod
    def _parameters(job: Job) -> dict[str, object]:
        value = decode_canonical_json(job.parameters_json)
        if not isinstance(value, dict) or value.get("schema") not in {
            "ronin.ml-execution.v1",
            "ronin.ml-execution.v2",
        }:
            raise ValueError("stored ML job parameters must be an object")
        return cast(dict[str, object], value)

    def create(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
        with self._writer_lease():
            return self._create(snapshot)

    def _create(self, snapshot: ExecutionSnapshot) -> ExecutionSnapshot:
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
            if self._artifact_reference_barrier is None:
                raise ValueError(
                    "artifact reference barrier is required for large async ML execution inputs"
                )
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
            "schema": "ronin.ml-execution.v2",
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
            "retry_of_run_id": snapshot.retry_of_run_id,
            "retry_from_stage": snapshot.retry_from_stage,
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
        created_parameters = self._parameters(created)
        if (
            created_parameters.get("retry_of_run_id") != snapshot.retry_of_run_id
            or created_parameters.get("retry_from_stage") != snapshot.retry_from_stage
        ):
            raise ExecutionConflict(f"execution request already exists: {snapshot.run_id}")
        return self.get(snapshot.workspace_id, snapshot.run_id) or snapshot

    def retry(
        self, workspace_id: str, source_run_id: str, retry_run_id: str, from_stage: str
    ) -> ExecutionSnapshot:
        if retry_run_id == source_run_id:
            raise ValueError("retry run_id must differ from the failed execution")
        if (
            not retry_run_id
            or retry_run_id != retry_run_id.strip()
            or len(retry_run_id) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in retry_run_id)
        ):
            raise ValueError("retry run_id must be 1 to 256 characters of trimmed text")
        if (
            not isinstance(from_stage, str)
            or not from_stage
            or from_stage != from_stage.strip()
            or len(from_stage) > 261
        ):
            raise ValueError("retry from_stage must be a pipeline stage id")
        source_job_id, _ = self._ids(workspace_id, source_run_id)
        source_job = asyncio.run(self._service.status(source_job_id))
        if (
            source_job is None
            or source_job.project_id != workspace_id
            or source_job.target != self.target
            or source_job.state is not JobState.FAILED
        ):
            raise ValueError("only a failed execution in this workspace can be retried")
        source_parameters = self._parameters(source_job)
        if (
            source_parameters.get("workspace_id") != workspace_id
            or source_parameters.get("run_id") != source_run_id
        ):
            raise ValueError("failed execution is not available in this workspace")
        pipeline_json = source_parameters.get("pipeline_json")
        if not isinstance(pipeline_json, str):
            raise ValueError("failed execution is missing its pinned pipeline")
        pipeline = PipelineIR.from_json(pipeline_json)
        if from_stage.startswith("node:"):
            stage_exists = any(node.id == from_stage[len("node:") :] for node in pipeline.nodes)
        else:
            stage_exists = any(
                node.kind == from_stage or node.id == from_stage for node in pipeline.nodes
            )
        if not stage_exists:
            supported_stages = {
                "profile",
                "quality_gate",
                "prepare",
                "train",
                "evaluate",
                "select",
                "register",
            }
            if from_stage not in supported_stages and "/" not in from_stage:
                raise ValueError("retry from_stage is not a supported ML stage")
            raise ValueError("retry from_stage is not present in the pinned pipeline")
        rows_json = cast(str | None, source_parameters.get("rows_json"))
        if rows_json is None and source_parameters.get("rows_artifact") is not None:
            rows_json = self._load_rows_artifact(source_parameters["rows_artifact"])
        if rows_json is None:
            raise ValueError("failed execution is missing its input snapshot")
        snapshot = ExecutionSnapshot(
            run_id=retry_run_id,
            state="queued",
            workspace_id=workspace_id,
            lab_id=str(source_parameters.get("lab_id", "")),
            lab_digest=str(source_parameters.get("lab_digest", "")),
            pipeline_digest=str(source_parameters.get("pipeline_digest", "")),
            request_digest=str(source_parameters.get("request_digest", "")),
            lab_json=cast(str | None, source_parameters.get("lab_json")),
            pipeline_json=pipeline_json,
            rows_json=rows_json,
            retry_of_run_id=source_run_id,
            retry_from_stage=from_stage,
        )
        return self.create(snapshot)

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
            # Keep the pinned graph on terminal snapshots so the API can expose
            # stage IDs/types for precise retries without returning node config.
            pipeline_json=cast(str | None, parameters.get("pipeline_json")),
            rows_json=cast(str | None, parameters.get("rows_json"))
            if state in {"queued", "running"}
            else None,
            retry_of_run_id=cast(str | None, parameters.get("retry_of_run_id")),
            retry_from_stage=cast(str | None, parameters.get("retry_from_stage")),
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
        stored_request_digest = parameters.get("request_digest")
        if (
            not isinstance(stored_request_digest, str)
            or stored_request_digest != claim.job.request_digest
        ):
            input_error = "stored ML request digest does not match the durable Job identity"
        rows_json = cast(str | None, parameters.get("rows_json"))
        if rows_json is None and parameters.get("rows_artifact") is not None:
            try:
                rows_json = self._load_rows_artifact(parameters["rows_artifact"])
            except Exception:
                input_error = "stored ML execution input artifact could not be verified"
        snapshot = ExecutionSnapshot(
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
            retry_of_run_id=cast(str | None, parameters.get("retry_of_run_id")),
            retry_from_stage=cast(str | None, parameters.get("retry_from_stage")),
        )
        return replace(snapshot, node_checkpoints=self.node_checkpoints(snapshot))

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

    @staticmethod
    def _node_cell_id(node_id: str) -> str:
        return "ml-node-" + hashlib.sha256(node_id.encode("utf-8")).hexdigest()

    def node_checkpoints(self, snapshot: ExecutionSnapshot) -> dict[str, object]:
        if not snapshot.pipeline_digest or not snapshot.request_digest:
            return {}
        source_run_id = snapshot.retry_of_run_id or snapshot.run_id
        job_id, _ = self._ids(snapshot.workspace_id, source_run_id)
        stored = asyncio.run(self._service.cell_results(job_id)) or ()
        checkpoints: dict[str, object] = {}
        invalidated_node_ids: set[str] = set()
        if snapshot.retry_from_stage is not None:
            if snapshot.pipeline_json is None:
                return {}
            pipeline = PipelineIR.from_json(snapshot.pipeline_json)
            invalidated_node_ids = _retry_invalidated_node_ids(
                pipeline, snapshot.retry_from_stage
            )
            if not invalidated_node_ids:
                return {}
        for cell in stored:
            if (
                not cell.cell_id.startswith("ml-node-")
                or cell.source_digest != snapshot.pipeline_digest
                or cell.execution_identity_digest != snapshot.request_digest
                or cell.state != "succeeded"
            ):
                continue
            try:
                decoded = decode_canonical_json(cell.result_json)
                if not isinstance(decoded, dict):
                    continue
                node_id_value = decoded.get("node_id")
                if not isinstance(node_id_value, str):
                    continue
                node_id = node_id_value
                if self._node_cell_id(node_id) != cell.cell_id:
                    continue
                if node_id in invalidated_node_ids:
                    continue
                checkpoint = decoded.get("checkpoint")
                artifact_value = decoded.get("artifact")
                if checkpoint is None and isinstance(artifact_value, dict):
                    checkpoint_bytes = self._load_checkpoint_artifact(artifact_value)
                    checkpoint_envelope = decode_canonical_json(checkpoint_bytes)
                    if (
                        not isinstance(checkpoint_envelope, dict)
                        or checkpoint_envelope.get("node_id") != node_id
                        or not isinstance(checkpoint_envelope.get("checkpoint"), dict)
                    ):
                        continue
                    checkpoint = checkpoint_envelope["checkpoint"]
                if isinstance(checkpoint, dict):
                    checkpoints[node_id] = checkpoint
            except (ValueError, TypeError):
                continue
        return checkpoints

    def _load_checkpoint_artifact(
        self,
        value: Mapping[str, object],
        *,
        expected_role: str = "ml-node-checkpoint",
    ) -> bytes:
        if self._artifact_store is None:
            raise ValueError("ML node checkpoint artifact store is unavailable")
        max_size_bytes = {
            "ml-node-checkpoint": MAX_NODE_CHECKPOINT_ARTIFACT_BYTES,
            "ml-plugin-stage-output": MAX_PLUGIN_STAGE_ARTIFACT_BYTES,
        }.get(expected_role)
        if max_size_bytes is None:
            raise ValueError("unsupported ML checkpoint artifact role")
        fields = {"role", "digest_algorithm", "digest", "media_type", "size_bytes", "storage_ref"}
        if set(value) != fields:
            raise ValueError("ML node checkpoint artifact reference is invalid")
        if (
            not isinstance(value["role"], str)
            or not isinstance(value["digest_algorithm"], str)
            or not isinstance(value["digest"], str)
            or (value["media_type"] is not None and not isinstance(value["media_type"], str))
            or not isinstance(value["size_bytes"], int)
            or isinstance(value["size_bytes"], bool)
            or not isinstance(value["storage_ref"], str)
        ):
            raise ValueError("ML node checkpoint artifact reference is invalid")
        ref = ArtifactRef(
            role=value["role"],
            digest_algorithm=value["digest_algorithm"],
            digest=value["digest"],
            media_type=cast(str | None, value["media_type"]),
            size_bytes=value["size_bytes"],
            storage_ref=value["storage_ref"],
        )
        if (
            ref.role != expected_role
            or ref.digest_algorithm != "sha256"
            or ref.media_type is None
            or (
                expected_role == "ml-node-checkpoint"
                and ref.media_type != "application/json"
            )
            or ref.size_bytes > max_size_bytes
            or ref.storage_ref != self._artifact_store.storage_ref_for_digest(ref.digest)
            or not self._artifact_store.verify(ref)
        ):
            raise ValueError("ML node checkpoint artifact failed verification")
        data = self._artifact_store.get_bytes(ref)
        if len(data) != ref.size_bytes or hashlib.sha256(data).hexdigest() != ref.digest:
            raise ValueError("ML node checkpoint artifact integrity check failed")
        return data

    def load_plugin_stage_artifact(self, value: Mapping[str, object]) -> bytes:
        """Read one verified artifact referenced by a durable plugin checkpoint."""
        data = self._load_checkpoint_artifact(
            value, expected_role="ml-plugin-stage-output"
        )
        if len(data) > MAX_PLUGIN_STAGE_ARTIFACT_BYTES:
            raise ValueError("ML plugin stage artifact exceeds the host byte limit")
        return data

    def save_plugin_stage_checkpoint(
        self,
        snapshot: ExecutionSnapshot,
        node_id: str,
        checkpoint: dict[str, object],
        artifacts: Mapping[str, tuple[str, bytes]],
    ) -> dict[str, dict[str, object]]:
        """Write plugin artifacts and their checkpoint reference under one lease."""
        if len(artifacts) > 8 or any(
            not isinstance(name, str)
            or not name
            or name != name.strip()
            or not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or "/" not in item[0]
            or not isinstance(item[1], bytes)
            for name, item in artifacts.items()
        ):
            raise ValueError("ML plugin stage artifacts have invalid metadata")
        if sum(len(data) for _, data in artifacts.values()) > MAX_PLUGIN_STAGE_ARTIFACT_BYTES:
            raise ValueError("ML plugin stage artifacts exceed the host limits")
        if artifacts and self._artifact_store is None:
            raise ValueError("artifact store is required for plugin stage outputs")
        if artifacts and self._artifact_reference_barrier is None:
            raise ValueError("artifact reference barrier is required for plugin stage outputs")
        with self._writer_lease():
            references: dict[str, dict[str, object]] = {}
            for name, (media_type, data) in sorted(artifacts.items()):
                artifact = self._artifact_store.put_bytes(
                    role="ml-plugin-stage-output", data=data, media_type=media_type
                )
                if (
                    artifact.role != "ml-plugin-stage-output"
                    or artifact.digest_algorithm != "sha256"
                    or artifact.media_type != media_type
                    or artifact.size_bytes != len(data)
                    or hashlib.sha256(data).hexdigest() != artifact.digest
                    or artifact.storage_ref
                    != self._artifact_store.storage_ref_for_digest(artifact.digest)
                    or not self._artifact_store.verify(artifact)
                ):
                    raise ValueError("ML plugin stage artifact failed verification after write")
                references[name] = {
                    "role": artifact.role,
                    "digest_algorithm": artifact.digest_algorithm,
                    "digest": artifact.digest,
                    "media_type": artifact.media_type,
                    "size_bytes": artifact.size_bytes,
                    "storage_ref": artifact.storage_ref,
                }
            payload = dict(checkpoint)
            payload["plugin_artifacts"] = references
            checkpoint_value = payload.get("checkpoint")
            if not isinstance(checkpoint_value, Mapping):
                raise ValueError("plugin checkpoint payload is invalid")
            checkpoint_value = dict(checkpoint_value)
            output_value = checkpoint_value.get("value")
            if not isinstance(output_value, Mapping):
                raise ValueError("plugin stage checkpoint output is invalid")
            payload["checkpoint"] = {
                **checkpoint_value,
                "value": {**dict(output_value), "__ronin_artifacts__": references},
            }
            persisted = self._save_node_checkpoint(
                snapshot, node_id, payload, retained_artifacts=references
            )
            if not persisted:
                raise ValueError("plugin checkpoint could not be persisted durably")
            return references

    def save_node_checkpoint(
        self, snapshot: ExecutionSnapshot, node_id: str, checkpoint: dict[str, object]
    ) -> bool:
        with self._writer_lease():
            return self._save_node_checkpoint(snapshot, node_id, checkpoint)

    def _save_node_checkpoint(
        self,
        snapshot: ExecutionSnapshot,
        node_id: str,
        checkpoint: dict[str, object],
        *,
        retained_artifacts: Mapping[str, Mapping[str, object]] | None = None,
    ) -> bool:
        if snapshot.attempt_id is None or snapshot.lease_token is None or snapshot.owner is None:
            raise ValueError("durable ML claim is missing its lease identity")
        if not snapshot.pipeline_digest or not snapshot.request_digest:
            raise ValueError("durable ML claim is missing its checkpoint identity")
        payload: dict[str, object] = {"node_id": node_id, "checkpoint": checkpoint}
        encoded = encode_canonical_json(payload)
        if len(encoded) > MAX_NODE_CHECKPOINT_ARTIFACT_BYTES:
            return False
        if len(encoded) > MAX_INLINE_NODE_CHECKPOINT_BYTES:
            if self._artifact_store is None:
                return False
            artifact = self._artifact_store.put_bytes(
                role="ml-node-checkpoint", data=encoded, media_type="application/json"
            )
            if (
                artifact.role != "ml-node-checkpoint"
                or artifact.digest_algorithm != "sha256"
                or artifact.media_type != "application/json"
                or artifact.size_bytes != len(encoded)
                or artifact.storage_ref
                != self._artifact_store.storage_ref_for_digest(artifact.digest)
                or not self._artifact_store.verify(artifact)
            ):
                raise ValueError("ML node checkpoint artifact failed verification after write")
            encoded = encode_canonical_json(
                {
                    "node_id": node_id,
                    "artifact": {
                        "role": artifact.role,
                        "digest_algorithm": artifact.digest_algorithm,
                        "digest": artifact.digest,
                        "media_type": artifact.media_type,
                        "size_bytes": artifact.size_bytes,
                        "storage_ref": artifact.storage_ref,
                    },
                    **(
                        {"plugin_artifacts": dict(retained_artifacts)}
                        if retained_artifacts
                        else {}
                    ),
                }
            )
        now = _now()
        _, run_id = self._ids(snapshot.workspace_id, snapshot.run_id)
        asyncio.run(
            self._service.worker_put_cell_result(
                AttemptId(snapshot.attempt_id),
                StoredCellResult(
                    run_id=run_id,
                    cell_id=self._node_cell_id(node_id),
                    source_digest=snapshot.pipeline_digest,
                    execution_identity_digest=snapshot.request_digest,
                    state="succeeded",
                    result_json=encoded.decode("utf-8"),
                    updated_at=now,
                ),
                owner=snapshot.owner,
                lease_token=LeaseToken(snapshot.lease_token),
                now=now,
            )
        )
        return True

    def _materialize_result_artifact(
        self, result: ExperimentResult | ClusteringResult
    ) -> dict[str, object]:
        """Persist a completed model as a verified ArtifactStore object."""
        if self._artifact_store is None:
            raise ValueError("artifact store is required to materialize ML model outputs")
        if isinstance(result, ExperimentResult):
            data = result.model.artifact_bytes
            media_type = "application/vnd.ronin.sklearn-tabular+json"
        else:
            data = json.dumps(
                result.model.to_artifact(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            media_type = "application/vnd.ronin.ml-kmeans+json"
        if len(data) > MAX_MATERIALIZED_MODEL_BYTES:
            raise ValueError(f"ML model artifact exceeds {MAX_MATERIALIZED_MODEL_BYTES} bytes")
        expected_digest = hashlib.sha256(data).hexdigest()
        if result.artifact_digest != f"sha256:{expected_digest}":
            raise ValueError("ML model artifact digest does not match the runner result")
        artifact = self._artifact_store.put_bytes(role="model", data=data, media_type=media_type)
        if (
            artifact.role != "model"
            or artifact.digest_algorithm != "sha256"
            or artifact.digest != expected_digest
            or artifact.media_type != media_type
            or artifact.size_bytes != len(data)
            or not artifact.storage_ref
            or not self._artifact_store.verify(artifact)
        ):
            raise ValueError("ML model artifact failed verification after materialization")
        stored = self._artifact_store.get_bytes(artifact)
        if len(stored) != len(data) or hashlib.sha256(stored).hexdigest() != expected_digest:
            raise ValueError("ML model artifact integrity check failed after materialization")
        payload = result.to_payload()
        payload["artifact_ref"] = artifact.storage_ref
        payload["artifact_media_type"] = media_type
        payload["artifact_size_bytes"] = artifact.size_bytes
        return payload

    def finish_claim_with_result(
        self,
        snapshot: ExecutionSnapshot,
        result: ExperimentResult | ClusteringResult,
        *,
        finalize_result: (
            Callable[[ExecutionSnapshot, dict[str, object]], dict[str, object]] | None
        ) = None,
    ) -> None:
        """Publish, optionally register, and commit a result while holding the writer lease."""
        with self._writer_lease():
            payload = self._materialize_result_artifact(result)
            if finalize_result is not None:
                payload = finalize_result(snapshot, payload)
            self.finish_claim(snapshot, state="succeeded", result_payload=payload)

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
        return replace(
            snapshot,
            state="cancelled",
            lab_json=None,
            pipeline_json=None,
            rows_json=None,
        )


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
        result_finalizer: Callable[[ExecutionSnapshot, dict[str, object]], dict[str, object]]
        | None = None,
    ) -> None:
        if max_workers < 1 or max_workers > 32:
            raise ValueError("max_workers must be between 1 and 32")
        self._runner = runner or LocalExperimentRunner()
        self._store = store or InMemoryExecutionStore()
        self._result_finalizer = result_finalizer
        self._owner = str(uuid4())
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ronin-ml")
        self._max_workers = max_workers
        self._lock = Lock()
        self._admission_lock = Lock()
        self._owned: dict[tuple[str, str], int] = {}
        self._claims: dict[tuple[str, str], ExecutionSnapshot] = {}
        self._active: set[tuple[str, str]] = set()
        self._futures: dict[tuple[str, str], Future[object]] = {}
        self._cancellations: dict[tuple[str, str], CancellationToken] = {}
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
                            token = self._cancellations.get(key)
                            if token is not None:
                                token.cancel()
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
                            self._cancellations[key] = CancellationToken()
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
                        token = self._cancellations.get((workspace_id, run_id))
                        if token is not None:
                            token.cancel()
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
                            self._cancellations[key] = CancellationToken()
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
                    self._cancellations.pop(key, None)

    def _execute(self, claimed: ExecutionSnapshot) -> object:
        key = (claimed.workspace_id, claimed.run_id)
        with self._lock:
            cancellation = self._cancellations.setdefault(key, CancellationToken())
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
            execute_pipeline = getattr(self._runner, "execute_pipeline", None)
            if callable(execute_pipeline):
                if isinstance(self._runner, LocalExperimentRunner) and isinstance(
                    self._store, JobStoreExecutionStore
                ):
                    result = execute_pipeline(
                        lab,
                        execution_rows,
                        pipeline,
                        checkpoint_load=(claimed.node_checkpoints or {}).get,
                        checkpoint_save=lambda node_id, payload: self._store.save_node_checkpoint(
                            claimed, node_id, payload
                        ),
                        cancellation=cancellation,
                        plugin_artifact_load=self._store.load_plugin_stage_artifact,
                        plugin_artifact_persist=lambda node_id, payload, artifacts: self._store.save_plugin_stage_checkpoint(
                            claimed, node_id, payload, artifacts
                        ),
                    )
                else:
                    result = execute_pipeline(lab, execution_rows, pipeline)
            elif lab.task == "clustering":
                if pipeline is not None and pipeline.digest != compile_lab_pipeline(lab).digest:
                    raise ValueError("runner cannot execute the submitted ML pipeline")
                result = self._runner.run_clustering_result(lab, execution_rows)
            else:
                if pipeline is not None and pipeline.digest != compile_lab_pipeline(lab).digest:
                    raise ValueError("runner cannot execute the submitted ML pipeline")
                result = self._runner.run(lab, execution_rows)
            if cancellation.is_cancelled:
                raise MLExecutionCancelled("ML pipeline execution was cancelled")
            if isinstance(self._store, JobStoreExecutionStore):
                if isinstance(result, (ExperimentResult, ClusteringResult)):
                    register_stage = pipeline is not None and any(
                        node.kind == "register" for node in pipeline.nodes
                    )
                    if register_stage and self._result_finalizer is None:
                        raise ValueError("pipeline register stage is unavailable")
                    finalizer = self._result_finalizer if register_stage else None
                    if register_stage and self._result_finalizer is not None:
                        result_finalizer = self._result_finalizer

                        def finalize_if_active(
                            snapshot: ExecutionSnapshot, payload: dict[str, object]
                        ) -> dict[str, object]:
                            if cancellation.is_cancelled:
                                raise MLExecutionCancelled(
                                    "ML pipeline execution was cancelled before registration"
                                )
                            return result_finalizer(snapshot, payload)

                        finalizer = finalize_if_active
                    self._store.finish_claim_with_result(
                        claimed,
                        result,
                        finalize_result=finalizer,
                    )
                else:
                    if pipeline is not None and any(
                        node.kind == "register" for node in pipeline.nodes
                    ):
                        raise ValueError("pipeline register stage requires a materialized model")
                    self._store.finish_claim(
                        claimed, state="succeeded", result_payload=result.to_payload()
                    )
                return result
            if pipeline is not None and any(node.kind == "register" for node in pipeline.nodes):
                raise ValueError("pipeline register stage requires durable artifact storage")
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
            if cancellation.is_cancelled and self._closing.is_set():
                # Closing the coordinator is not a user cancellation. Leave the
                # durable lease to expire so another worker can resume it.
                return None
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
        with self._lock:
            token = self._cancellations.get((workspace_id, run_id))
            if token is not None:
                token.cancel()
        snapshot = self._store.cancel(workspace_id, run_id)
        with self._lock:
            self._owned.pop((workspace_id, run_id), None)
            self._cancellations.pop((workspace_id, run_id), None)
        return snapshot

    def retry(
        self, workspace_id: str, source_run_id: str, retry_run_id: str, from_stage: str
    ) -> ExecutionSnapshot:
        if not isinstance(self._store, JobStoreExecutionStore):
            raise ValueError("selective ML retry requires durable JobStore execution storage")
        return self._store.retry(workspace_id, source_run_id, retry_run_id, from_stage)

    def close(self) -> None:
        self._closing.set()
        self._stop.set()
        with self._lock:
            for token in self._cancellations.values():
                token.cancel()
        with self._admission_lock:
            pass
        if self._started:
            self._poller.join(timeout=5)
        self._executor.shutdown(wait=True, cancel_futures=False)


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
    "MAX_MATERIALIZED_MODEL_BYTES",
    "RunState",
]
