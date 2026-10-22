"""The ML adapter maps requests onto the host's canonical JobStore lifecycle."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace

import pytest
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_execution import DurableExecutionService
from studio_ml import ExecutionConflict, ExecutionSnapshot, JobStoreExecutionStore
from studio_ml.orchestration import MAX_INLINE_EXECUTION_REQUEST_BYTES
from studio_orchestrator import Instant, JobState
from studio_storage import InMemoryJobStore, LocalArtifactStore, SqliteJobStore


def _snapshot(
    workspace_id: str, digest: str = "a" * 64, rows_json: str = "[]"
) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        run_id="shared-run",
        state="queued",
        workspace_id=workspace_id,
        lab_id="lab-1",
        lab_digest="b" * 64,
        request_digest=digest,
        lab_json="{}",
        rows_json=rows_json,
    )


def test_job_store_adapter_scopes_and_idempotently_replays_requests() -> None:
    service = DurableExecutionService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(service)
    try:
        first = adapter.create(_snapshot("workspace-a"))
        replay = adapter.create(_snapshot("workspace-a"))
        other_workspace = adapter.create(_snapshot("workspace-b", "c" * 64))

        assert first.state == "queued"
        assert replay.state == "queued"
        assert other_workspace.workspace_id == "workspace-b"
        assert (
            JobStoreExecutionStore._ids("workspace-a", "shared-run")[0]
            != (JobStoreExecutionStore._ids("workspace-b", "shared-run")[0])
        )
        with pytest.raises(ExecutionConflict, match="already exists"):
            adapter.create(_snapshot("workspace-a", "d" * 64))

        page = asyncio.run(
            service.list_jobs(
                project_id=None,
                project_ids=None,
                state=JobState.QUEUED,
                limit=10,
                cursor=None,
            )
        )
        assert len(page.items) == 2
    finally:
        asyncio.run(service.aclose())


def test_large_execution_rows_are_artifact_backed_and_recover_after_store_reopen(
    tmp_path,
) -> None:
    rows_json = encode_canonical_json([{"large": "x" * MAX_INLINE_EXECUTION_REQUEST_BYTES}]).decode(
        "utf-8"
    )
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    jobs_path = tmp_path / "jobs.sqlite"
    migration_now = Instant("2026-10-19T00:00:00.000000Z")
    service = DurableExecutionService(SqliteJobStore(jobs_path, migration_now=migration_now))
    adapter = JobStoreExecutionStore(service, artifacts)
    try:
        adapter.create(_snapshot("workspace-a", rows_json=rows_json))
        job_id, _ = adapter._ids("workspace-a", "shared-run")
        job = asyncio.run(service.status(job_id))
        assert job is not None
        parameters = decode_canonical_json(job.parameters_json)
        assert isinstance(parameters, dict)
        assert parameters["rows_json"] is None
        assert isinstance(parameters["rows_artifact"], dict)
        assert len(job.parameters_json.encode("utf-8")) < 10_000
    finally:
        asyncio.run(service.aclose())

    reopened = DurableExecutionService(SqliteJobStore(jobs_path, migration_now=migration_now))
    reopened_adapter = JobStoreExecutionStore(reopened, artifacts)
    try:
        claim = reopened_adapter.claim_next("worker-a")
        assert claim is not None
        assert claim.rows_json == rows_json
        assert claim.input_error is None
    finally:
        asyncio.run(reopened.aclose())


def test_ml_input_artifact_and_job_reference_share_writer_lease(tmp_path) -> None:
    events: list[str] = []

    class _Barrier:
        @contextmanager
        def writer(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

        @contextmanager
        def collector(self):
            yield

    class _RecordingArtifacts:
        def __init__(self) -> None:
            self._inner = LocalArtifactStore(tmp_path / "artifacts")

        def put_bytes(self, **kwargs):
            events.append("artifact")
            return self._inner.put_bytes(**kwargs)

        def verify(self, ref):
            return self._inner.verify(ref)

        def get_bytes(self, ref):
            return self._inner.get_bytes(ref)

        def delete(self, ref):
            return self._inner.delete(ref)

        def list_digests(self):
            return self._inner.list_digests()

        def storage_ref_for_digest(self, digest):
            return self._inner.storage_ref_for_digest(digest)

    class _RecordingService(DurableExecutionService):
        async def submit(self, job, run):
            events.append("reference")
            return await super().submit(job, run)

    service = _RecordingService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(
        service,
        _RecordingArtifacts(),
        artifact_reference_barrier=_Barrier(),
    )
    rows_json = encode_canonical_json([{"large": "x" * MAX_INLINE_EXECUTION_REQUEST_BYTES}])
    try:
        adapter.create(_snapshot("workspace-a", rows_json=rows_json.decode("utf-8")))
        assert events == ["lock", "artifact", "reference", "unlock"]
    finally:
        asyncio.run(service.aclose())


def test_plugin_stage_artifact_and_checkpoint_share_writer_lease(tmp_path) -> None:
    events: list[str] = []

    class _Barrier:
        @contextmanager
        def writer(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

        @contextmanager
        def collector(self):
            yield

    class _RecordingArtifacts:
        def __init__(self) -> None:
            self._inner = LocalArtifactStore(tmp_path / "plugin-artifacts")

        def put_bytes(self, **kwargs):
            events.append("artifact")
            return self._inner.put_bytes(**kwargs)

        def verify(self, ref):
            return self._inner.verify(ref)

        def get_bytes(self, ref):
            return self._inner.get_bytes(ref)

        def delete(self, ref):
            return self._inner.delete(ref)

        def list_digests(self):
            return self._inner.list_digests()

        def storage_ref_for_digest(self, digest):
            return self._inner.storage_ref_for_digest(digest)

    class _RecordingService(DurableExecutionService):
        async def worker_put_cell_result(self, *args, **kwargs):
            events.append("checkpoint")
            return await super().worker_put_cell_result(*args, **kwargs)

    service = _RecordingService(InMemoryJobStore())
    artifacts = _RecordingArtifacts()
    adapter = JobStoreExecutionStore(
        service,
        artifacts,
        artifact_reference_barrier=_Barrier(),
    )
    try:
        queued = replace(_snapshot("workspace-a"), pipeline_digest="c" * 64)
        adapter.create(queued)
        events.clear()
        claimed = adapter.claim_next("worker-a")
        assert claimed is not None
        refs = adapter.save_plugin_stage_checkpoint(
            claimed,
            "plugin-metrics",
            {
                "runtime_fingerprint": "d" * 64,
                "dependency_fingerprint": "e" * 64,
                "checkpoint_codec": "ronin.ml.plugin-checkpoint/v1",
                "checkpoint": {"kind": "com.example.ml/metrics", "value": {"scores": {}}},
            },
            {"metrics.json": ("application/json", b'{"accuracy":1.0}')},
        )
        assert events == ["lock", "artifact", "checkpoint", "unlock"]
        assert adapter.load_plugin_stage_artifact(refs["metrics.json"]) == b'{"accuracy":1.0}'
        checkpoints = adapter.node_checkpoints(claimed)
        assert checkpoints["plugin-metrics"]["checkpoint"]["value"][
            "__ronin_artifacts__"
        ] == refs
    finally:
        asyncio.run(service.aclose())


def test_large_execution_rows_require_artifact_store_before_job_submission() -> None:
    rows_json = encode_canonical_json([{"large": "x" * MAX_INLINE_EXECUTION_REQUEST_BYTES}]).decode(
        "utf-8"
    )
    service = DurableExecutionService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(service)
    try:
        with pytest.raises(ValueError, match="artifact store is required"):
            adapter.create(_snapshot("workspace-a", rows_json=rows_json))
        page = asyncio.run(
            service.list_jobs(
                project_id=None,
                project_ids=None,
                state=JobState.QUEUED,
                limit=10,
                cursor=None,
            )
        )
        assert page.items == ()
    finally:
        asyncio.run(service.aclose())


def test_ml_node_checkpoints_are_fenced_and_bound_to_pipeline_and_request() -> None:
    service = DurableExecutionService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(service)
    try:
        queued = replace(_snapshot("workspace-a"), pipeline_digest="c" * 64)
        adapter.create(queued)
        claimed = adapter.claim_next("worker-a")
        assert claimed is not None
        adapter.save_node_checkpoint(
            claimed,
            "profile",
            {"kind": "profile", "value": {"row_count": 20}},
        )
        assert adapter.node_checkpoints(claimed) == {
            "profile": {"kind": "profile", "value": {"row_count": 20}}
        }
        assert adapter.node_checkpoints(replace(claimed, request_digest="d" * 64)) == {}
        assert adapter.node_checkpoints(replace(claimed, pipeline_digest="e" * 64)) == {}
    finally:
        asyncio.run(service.aclose())


def test_large_ml_node_checkpoint_uses_verified_artifact_storage(tmp_path) -> None:
    service = DurableExecutionService(InMemoryJobStore())
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    adapter = JobStoreExecutionStore(service, artifacts)
    try:
        queued = replace(_snapshot("workspace-a"), pipeline_digest="c" * 64)
        adapter.create(queued)
        claimed = adapter.claim_next("worker-a")
        assert claimed is not None
        checkpoint = {"kind": "profile", "value": {"large": "x" * 300_000}}
        adapter.save_node_checkpoint(claimed, "profile", checkpoint)
        assert adapter.node_checkpoints(claimed) == {"profile": checkpoint}
        stored = asyncio.run(service.cell_results(adapter._ids("workspace-a", "shared-run")[0]))
        assert stored is not None
        assert len(stored) == 1
        assert len(stored[0].result_json) < 2_000
    finally:
        asyncio.run(service.aclose())


def test_large_ml_node_checkpoint_is_skipped_when_artifact_storage_is_unavailable() -> None:
    service = DurableExecutionService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(service)
    try:
        queued = replace(_snapshot("workspace-a"), pipeline_digest="c" * 64)
        adapter.create(queued)
        claimed = adapter.claim_next("worker-a")
        assert claimed is not None
        assert (
            adapter.save_node_checkpoint(
                claimed,
                "train",
                {"kind": "train", "value": {"large": "x" * 300_000}},
            )
            is False
        )
        assert adapter.node_checkpoints(claimed) == {}
    finally:
        asyncio.run(service.aclose())


def test_large_execution_artifact_is_rehashed_after_store_read(tmp_path) -> None:
    class CorruptingArtifactStore:
        def __init__(self) -> None:
            self.inner = LocalArtifactStore(tmp_path / "artifacts")

        def put_bytes(self, **kwargs):
            return self.inner.put_bytes(**kwargs)

        def verify(self, _ref) -> bool:
            return True

        def get_bytes(self, ref):
            data = self.inner.get_bytes(ref)
            return b"!" + data[1:]

    rows_json = encode_canonical_json([{"large": "x" * MAX_INLINE_EXECUTION_REQUEST_BYTES}]).decode(
        "utf-8"
    )
    service = DurableExecutionService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(service, CorruptingArtifactStore())
    try:
        adapter.create(_snapshot("workspace-a", rows_json=rows_json))
        claim = adapter.claim_next("worker-a")
        assert claim is not None
        assert claim.rows_json is None
        assert claim.input_error == "stored ML execution input artifact could not be verified"
        adapter.finish_claim(claim, state="failed", error=claim.input_error)
        status = adapter.get("workspace-a", "shared-run")
        assert status is not None
        assert status.state == "failed"
        assert status.error == claim.input_error
    finally:
        asyncio.run(service.aclose())
