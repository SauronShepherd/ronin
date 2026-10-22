"""Asynchronous ML Studio lifecycle tests."""
# ruff: noqa: E501

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import replace
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_execution import DurableExecutionService
from studio_ml.clustering import KMeansModel
from studio_ml.domain import PIPELINE_SCHEMA_V2, FeatureSpec, Lab, PipelineIR, PipelineNode
from studio_ml.orchestration import (
    ClusteringResult,
    ExecutionConflict,
    ExecutionSnapshot,
    InMemoryExecutionStore,
    JobStoreExecutionStore,
    LocalExecutionCoordinator,
)
from studio_ml.runner import ExperimentResult, LocalExperimentRunner
from studio_ml.runtime import TrainedTabularModel, train_tabular
from studio_ml.services import compile_lab_pipeline
from studio_orchestrator import Instant
from studio_storage import LocalArtifactStore, SqliteJobStore

LOCAL_ML_TIMEOUT = 90 if os.name == "nt" else 30
_MIGRATION_NOW = Instant("2026-10-19T00:00:00.000000Z")


def _active_future(coordinator: LocalExecutionCoordinator, key: tuple[str, str]):
    deadline = time.monotonic() + 5
    while key not in coordinator._futures and time.monotonic() < deadline:
        time.sleep(0.001)
    return coordinator._futures[key]


def test_local_coordinator_reaches_terminal_state() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit("ws", "run-1", lab, [{"x": n, "target": n % 2} for n in range(1, 21)])
        # First-use sklearn imports can exceed five seconds on a cold Windows host.
        deadline = time.time() + LOCAL_ML_TIMEOUT
        while (
            coordinator.status("ws", "run-1").state not in {"succeeded", "failed"}
            and time.time() < deadline
        ):
            time.sleep(0.01)
        assert coordinator.status("ws", "run-1").state == "succeeded"
    finally:
        coordinator.close()


def test_ml_execution_uses_shared_sqlite_job_lifecycle_and_persists_result(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class ImmediateRunner:
        def run(self, _lab, _rows):
            return SimpleNamespace(to_payload=lambda: {"accuracy": 1.0})

    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    coordinator = LocalExecutionCoordinator(
        runner=ImmediateRunner(), store=JobStoreExecutionStore(service)
    )
    try:
        coordinator.submit("workspace-a", "shared-id", lab, [{"x": 1, "target": 1}])
        coordinator.submit("workspace-b", "shared-id", lab, [{"x": 2, "target": 0}])
        deadline = time.time() + 10
        while time.time() < deadline:
            states = {
                coordinator.status(workspace, "shared-id").state
                for workspace in ("workspace-a", "workspace-b")
            }
            if states == {"succeeded"}:
                break
            time.sleep(0.01)
        assert states == {"succeeded"}
        assert coordinator.status("workspace-a", "shared-id").result_payload == {"accuracy": 1.0}
        with pytest.raises(ExecutionConflict, match="already exists"):
            coordinator.submit("workspace-a", "shared-id", lab, [{"x": 3, "target": 1}])
        first_id, _ = JobStoreExecutionStore._ids("workspace-a", "shared-id")
        second_id, _ = JobStoreExecutionStore._ids("workspace-b", "shared-id")
        assert first_id != second_id
    finally:
        coordinator.close()
        import asyncio

        asyncio.run(service.aclose())


def test_large_async_execution_uses_artifact_input_and_completes(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class ImmediateRunner:
        def run(self, _lab, rows):
            return SimpleNamespace(to_payload=lambda: {"input_bytes": len(rows[0]["large"])})

    migration_now = _MIGRATION_NOW
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=migration_now)
    service = DurableExecutionService(jobs)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    adapter = JobStoreExecutionStore(service, artifacts)
    coordinator = LocalExecutionCoordinator(runner=ImmediateRunner(), store=adapter)
    try:
        coordinator.submit(
            "workspace-a",
            "large-input",
            lab,
            [{"large": "x" * 1_100_000, "target": 1}],
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            result = coordinator.status("workspace-a", "large-input")
            if result.state in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert result.state == "succeeded"
        assert result.result_payload == {"input_bytes": 1_100_000}
    finally:
        coordinator.close()
        import asyncio

        asyncio.run(service.aclose())


def test_shared_job_store_cancel_fences_ml_worker_write(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    adapter = JobStoreExecutionStore(service)
    try:
        adapter.create(
            ExecutionSnapshot(
                run_id="cancel-me",
                state="queued",
                workspace_id="workspace-a",
                lab_id=lab.id,
                lab_digest=lab.digest,
                request_digest=hashlib.sha256(b"request").hexdigest(),
                lab_json=lab.to_json(),
                rows_json=encode_canonical_json([{"x": 1, "target": 1}]).decode(),
            )
        )
        claim = adapter.claim_next("worker-a")
        assert claim is not None
        cancelled = adapter.cancel("workspace-a", "cancel-me")
        assert cancelled.state == "cancelled"
        with pytest.raises(Exception, match="lease|ownership|cancel|terminal"):
            adapter.finish_claim(claim, state="succeeded", result_payload={"late": True})
        status = adapter.get("workspace-a", "cancel-me")
        assert status is not None
        assert status.state == "cancelled"
    finally:
        import asyncio

        asyncio.run(service.aclose())


def test_shared_job_store_reopens_and_idempotent_retry_does_not_duplicate_job(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class ImmediateRunner:
        def run(self, _lab, _rows):
            return SimpleNamespace(to_payload=lambda: {"recovered": True})

    path = tmp_path / "jobs.sqlite"
    service = DurableExecutionService(SqliteJobStore(path, migration_now=_MIGRATION_NOW))
    adapter = JobStoreExecutionStore(service)
    rows = [{"x": 1, "target": 1}]
    request_digest = hashlib.sha256(
        encode_canonical_json({"lab": lab.to_payload(), "rows": rows})
    ).hexdigest()
    first = adapter.create(
        ExecutionSnapshot(
            run_id="recoverable",
            state="queued",
            workspace_id="workspace-a",
            lab_id=lab.id,
            lab_digest=lab.digest,
            request_digest=request_digest,
            lab_json=lab.to_json(),
            rows_json=encode_canonical_json(rows).decode(),
        )
    )
    import asyncio

    asyncio.run(service.aclose())

    reopened_service = DurableExecutionService(SqliteJobStore(path, migration_now=_MIGRATION_NOW))
    reopened_adapter = JobStoreExecutionStore(reopened_service)
    coordinator = LocalExecutionCoordinator(runner=ImmediateRunner(), store=reopened_adapter)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            recovered = coordinator.status("workspace-a", "recoverable")
            if recovered.state in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert recovered.state == "succeeded"
        replay = reopened_adapter.create(
            ExecutionSnapshot(
                run_id="recoverable",
                state="queued",
                workspace_id="workspace-a",
                lab_id=lab.id,
                lab_digest=lab.digest,
                request_digest=first.request_digest,
                lab_json=lab.to_json(),
                rows_json=encode_canonical_json(rows).decode(),
            )
        )
        assert replay.state == "succeeded"
        from studio_orchestrator import JobState

        page = asyncio.run(
            reopened_service.list_jobs(
                project_id="workspace-a",
                project_ids=None,
                state=JobState.SUCCEEDED,
                limit=10,
                cursor=None,
            )
        )
        assert len(page.items) == 1
    finally:
        coordinator.close()
        asyncio.run(reopened_service.aclose())


def test_selective_retry_reuses_upstream_checkpoints_and_retrains_from_selected_stage(
    tmp_path, monkeypatch
) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]

    class FailFirstTraining:
        backend_id = "local.sklearn"
        display_name = "retry test backend"
        capabilities = None

        def __init__(self):
            self.train_calls = 0

        def train(self, request, training_rows):
            self.train_calls += 1
            if self.train_calls == 1:
                raise RuntimeError("transient training failure")
            return train_tabular(training_rows, request.spec)

    import studio_ml.runner as runner_module

    profile_calls = 0
    original_profile = runner_module.profile_and_validate

    def count_profiles(*args, **kwargs):
        nonlocal profile_calls
        profile_calls += 1
        return original_profile(*args, **kwargs)

    monkeypatch.setattr(runner_module, "profile_and_validate", count_profiles)
    jobs = SqliteJobStore(tmp_path / "selective-retry.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    backend = FailFirstTraining()
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    adapter = JobStoreExecutionStore(service, artifacts)
    coordinator = LocalExecutionCoordinator(runner=LocalExperimentRunner((backend,)), store=adapter)
    try:
        coordinator.submit("workspace-a", "failed-run", lab, rows)
        deadline = time.monotonic() + LOCAL_ML_TIMEOUT
        failed = coordinator.status("workspace-a", "failed-run")
        while failed.state not in {"failed", "succeeded"} and time.monotonic() < deadline:
            time.sleep(0.01)
            failed = coordinator.status("workspace-a", "failed-run")
        assert failed.state == "failed"
        assert "transient training failure" in (failed.error or "")
        assert profile_calls == 1
        with pytest.raises(ValueError, match="only a failed execution"):
            coordinator.retry("workspace-b", "failed-run", "wrong-workspace-retry", "train")
        with pytest.raises(ValueError, match="supported ML stage"):
            coordinator.retry("workspace-a", "failed-run", "unknown-stage-retry", "publish")
        with pytest.raises(ValueError, match="trimmed text"):
            coordinator.retry("workspace-a", "failed-run", "bad\nretry", "train")

        retried = coordinator.retry("workspace-a", "failed-run", "failed-run-retry-1", "train")
        assert retried.state == "queued"
        assert retried.retry_of_run_id == "failed-run"
        assert retried.retry_from_stage == "train"
        deadline = time.monotonic() + LOCAL_ML_TIMEOUT
        completed = coordinator.status("workspace-a", "failed-run-retry-1")
        while completed.state not in {"failed", "succeeded"} and time.monotonic() < deadline:
            time.sleep(0.01)
            completed = coordinator.status("workspace-a", "failed-run-retry-1")
        assert completed.state == "succeeded", completed.error
        assert completed.result_payload is not None
        assert completed.retry_of_run_id == "failed-run"
        assert completed.retry_from_stage == "train"
        assert profile_calls == 1
        assert backend.train_calls == 2
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_durable_ml_result_materializes_and_verifies_model_artifact(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    artifact_bytes = b'{"schema":"ronin.ml-tabular/v1"}'
    model = TrainedTabularModel(
        "classification",
        "LogisticRegression",
        ("x",),
        "target",
        artifact_bytes,
        (("accuracy", 1.0),),
    )
    result = ExperimentResult(
        lab.id,
        "local.sklearn",
        4,
        model,
        f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}",
    )

    class ResultRunner:
        def run(self, _lab, _rows):
            return result

    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    events: list[str] = []

    class RecordingService(DurableExecutionService):
        async def worker_put_cell_result(self, *_args, **_kwargs):
            events.append("reference")
            return await super().worker_put_cell_result(*_args, **_kwargs)

    class RecordingArtifacts:
        def __init__(self, inner):
            self._inner = inner

        def put_bytes(self, **kwargs):
            events.append("artifact")
            return self._inner.put_bytes(**kwargs)

        def verify(self, ref):
            return self._inner.verify(ref)

        def get_bytes(self, ref):
            return self._inner.get_bytes(ref)

    class RecordingBarrier:
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

    service = RecordingService(jobs)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    coordinator = LocalExecutionCoordinator(
        runner=ResultRunner(),
        store=JobStoreExecutionStore(
            service,
            RecordingArtifacts(artifacts),
            artifact_reference_barrier=RecordingBarrier(),
        ),
    )
    try:
        coordinator.submit("workspace-a", "materialized-run", lab, [{"x": 1, "target": 1}])
        deadline = time.monotonic() + 10
        snapshot = coordinator.status("workspace-a", "materialized-run")
        while snapshot.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = coordinator.status("workspace-a", "materialized-run")
        assert snapshot.state == "succeeded", snapshot.error
        artifact_index = events.index("artifact")
        reference_index = events.index("reference")
        assert events[artifact_index - 1] == "lock"
        assert events[reference_index + 1] == "unlock"
        assert snapshot.result_payload is not None
        assert snapshot.result_payload["artifact_digest"] == result.artifact_digest
        assert snapshot.result_payload["artifact_ref"] == (
            f"artifact://sha256/{hashlib.sha256(artifact_bytes).hexdigest()}"
        )
        assert snapshot.result_payload["artifact_media_type"] == (
            "application/vnd.ronin.sklearn-tabular+json"
        )
        assert (
            artifacts.get_bytes_by_storage_ref(
                str(snapshot.result_payload["artifact_ref"]),
                digest=hashlib.sha256(artifact_bytes).hexdigest(),
            )
            == artifact_bytes
        )
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_pipeline_registration_is_idempotent_across_durable_retry(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    compiled = compile_lab_pipeline(
        lab, candidate_algorithms=("logistic_regression", "decision_tree_classifier")
    )
    pipeline = PipelineIR(
        (
            *compiled.nodes,
            PipelineNode(
                "register",
                "register",
                ("select",),
                {"model_id": "churn", "version": "candidate-1"},
            ),
        ),
        parameters=compiled.parameters,
        schema=PIPELINE_SCHEMA_V2,
    )
    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    registered: dict[tuple[str, str], dict[str, object]] = {}
    events: list[str] = []
    finalizer_calls = 0

    class RecordingBarrier:
        @contextmanager
        def writer(self):
            events.append("writer-lock")
            try:
                yield
            finally:
                events.append("writer-unlock")

        @contextmanager
        def collector(self):
            yield

    def finalize(_snapshot, payload):
        nonlocal finalizer_calls
        finalizer_calls += 1
        events.append("register")
        key = ("churn", "candidate-1")
        model = registered.setdefault(
            key,
            {
                "model_id": key[0],
                "version": key[1],
                "artifact_ref": payload["artifact_ref"],
            },
        )
        if finalizer_calls == 1:
            raise RuntimeError("simulated worker loss after idempotent registration")
        return {**payload, "registered_model": model}

    coordinator = LocalExecutionCoordinator(
        runner=LocalExperimentRunner(),
        store=JobStoreExecutionStore(
            service, artifacts, artifact_reference_barrier=RecordingBarrier()
        ),
        result_finalizer=finalize,
    )
    try:
        coordinator.submit("workspace-a", "register-run", lab, rows, pipeline)
        deadline = time.monotonic() + LOCAL_ML_TIMEOUT
        failed = coordinator.status("workspace-a", "register-run")
        while failed.state not in {"failed", "succeeded"} and time.monotonic() < deadline:
            time.sleep(0.01)
            failed = coordinator.status("workspace-a", "register-run")
        assert failed.state == "failed"
        assert len(registered) == 1

        coordinator.retry("workspace-a", "register-run", "register-retry", "register")
        deadline = time.monotonic() + LOCAL_ML_TIMEOUT
        completed = coordinator.status("workspace-a", "register-retry")
        while completed.state not in {"failed", "succeeded"} and time.monotonic() < deadline:
            time.sleep(0.01)
            completed = coordinator.status("workspace-a", "register-retry")
        assert completed.state == "succeeded", completed.error
        assert completed.result_payload is not None
        assert completed.result_payload["registered_model"] == next(iter(registered.values()))
        assert finalizer_calls == 2
        assert len(registered) == 1
        assert events[-3:] == ["writer-lock", "register", "writer-unlock"]
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_durable_ml_result_rejects_mismatched_model_artifact_digest(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    model = TrainedTabularModel(
        "classification",
        "LogisticRegression",
        ("x",),
        "target",
        b'{"schema":"ronin.ml-tabular/v1"}',
        (("accuracy", 1.0),),
    )
    result = ExperimentResult(lab.id, "local.sklearn", 4, model, "sha256:" + "0" * 64)

    class ResultRunner:
        def run(self, _lab, _rows):
            return result

    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    coordinator = LocalExecutionCoordinator(
        runner=ResultRunner(),
        store=JobStoreExecutionStore(service, artifacts),
    )
    try:
        coordinator.submit("workspace-a", "bad-result-digest", lab, [{"x": 1, "target": 1}])
        deadline = time.monotonic() + 10
        snapshot = coordinator.status("workspace-a", "bad-result-digest")
        while snapshot.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = coordinator.status("workspace-a", "bad-result-digest")
        assert snapshot.state == "failed"
        assert snapshot.error == "ML model artifact digest does not match the runner result"
        assert artifacts.list_digests() == ()
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_durable_clustering_result_materializes_canonical_model_artifact(tmp_path) -> None:
    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        None,
        "clustering",
        (FeatureSpec("x"),),
    )
    model = KMeansModel(((0.5,), (9.5,)), 3)
    artifact_bytes = json.dumps(model.to_artifact(), sort_keys=True, separators=(",", ":")).encode()
    result = ClusteringResult(
        lab.id,
        "local.kmeans",
        4,
        ("x",),
        model,
        f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}",
        1.0,
    )

    class ResultRunner:
        def run_clustering_result(self, _lab, _rows):
            return result

    jobs = SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(jobs)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    coordinator = LocalExecutionCoordinator(
        runner=ResultRunner(),
        store=JobStoreExecutionStore(service, artifacts),
    )
    try:
        coordinator.submit("workspace-a", "cluster-materialized", lab, [{"x": 0.5}])
        deadline = time.monotonic() + 10
        snapshot = coordinator.status("workspace-a", "cluster-materialized")
        while snapshot.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            snapshot = coordinator.status("workspace-a", "cluster-materialized")
        assert snapshot.state == "succeeded", snapshot.error
        assert snapshot.result_payload is not None
        assert snapshot.result_payload["artifact_digest"] == result.artifact_digest
        assert snapshot.result_payload["artifact_media_type"] == (
            "application/vnd.ronin.ml-kmeans+json"
        )
        assert (
            artifacts.get_bytes_by_storage_ref(
                str(snapshot.result_payload["artifact_ref"]),
                digest=hashlib.sha256(artifact_bytes).hexdigest(),
            )
            == artifact_bytes
        )
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_shared_job_store_preserves_failure_reason(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class FailingRunner:
        def run(self, _lab, _rows):
            raise RuntimeError("training failed with a useful reason")

    import asyncio

    service = DurableExecutionService(
        SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    )
    coordinator = LocalExecutionCoordinator(
        runner=FailingRunner(), store=JobStoreExecutionStore(service)
    )
    try:
        coordinator.submit("workspace-a", "failed-run", lab, [{"x": 1, "target": 1}])
        deadline = time.time() + 5
        while time.time() < deadline:
            failed = coordinator.status("workspace-a", "failed-run")
            if failed.state in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert failed.state == "failed"
        assert failed.error == "training failed with a useful reason"
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_local_coordinator_scopes_duplicate_run_ids_and_rejects_changed_retries() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    rows = [{"x": n, "target": n % 2} for n in range(1, 21)]
    coordinator = LocalExecutionCoordinator()
    try:
        first = coordinator.submit("workspace-a", "shared-run", lab, rows)
        again = coordinator.submit("workspace-a", "shared-run", lab, rows)
        other = coordinator.submit("workspace-b", "shared-run", lab, rows)
        assert first.request_digest == again.request_digest
        assert other.workspace_id == "workspace-b"
        with pytest.raises(ExecutionConflict, match="already exists"):
            coordinator.submit("workspace-a", "shared-run", lab, rows[:-1])

        deadline = time.time() + LOCAL_ML_TIMEOUT
        while time.time() < deadline:
            states = {
                coordinator.status("workspace-a", "shared-run").state,
                coordinator.status("workspace-b", "shared-run").state,
            }
            if states == {"succeeded"}:
                break
            time.sleep(0.01)
        assert coordinator.status("workspace-a", "shared-run").state == "succeeded"
        assert coordinator.status("workspace-b", "shared-run").state == "succeeded"
    finally:
        coordinator.close()


def test_pipeline_definition_is_pinned_in_durable_request_and_recovery(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    service = DurableExecutionService(
        SqliteJobStore(tmp_path / "jobs.sqlite", migration_now=_MIGRATION_NOW)
    )
    coordinator = LocalExecutionCoordinator(
        runner=SimpleNamespace(),
        store=JobStoreExecutionStore(service),
        autostart=False,
    )
    try:
        submitted = coordinator.submit("workspace-a", "pipeline-pinned", lab, [{"x": 1}])
        pipeline = PipelineIR.from_json(submitted.pipeline_json or "")
        assert submitted.pipeline_digest == pipeline.digest
        assert dict(pipeline.parameters)["lab_digest"] == submitted.lab_digest == lab.digest
        assert (
            submitted.request_digest
            == hashlib.sha256(
                encode_canonical_json(
                    {"lab": lab.to_payload(), "pipeline": pipeline.to_payload(), "rows": [{"x": 1}]}
                )
            ).hexdigest()
        )
        persisted = JobStoreExecutionStore(service).get("workspace-a", "pipeline-pinned")
        assert persisted is not None
        assert persisted.pipeline_json == submitted.pipeline_json
        assert persisted.pipeline_digest == submitted.pipeline_digest
    finally:
        coordinator.close()
        import asyncio

        asyncio.run(service.aclose())


def test_pipeline_definition_change_conflicts_for_same_durable_run() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator(autostart=False)
    try:
        pipeline = compile_lab_pipeline(lab)
        coordinator.submit("workspace-a", "pipeline-change", lab, [{"x": 1}], pipeline)
        changed_pipeline = PipelineIR(
            nodes=pipeline.nodes,
            parameters=(*pipeline.parameters, ("revision", "changed")),
        )
        with pytest.raises(ExecutionConflict, match="already exists"):
            coordinator.submit("workspace-a", "pipeline-change", lab, [{"x": 1}], changed_pipeline)
    finally:
        coordinator.close()


def test_claim_rejects_pipeline_and_digest_rewritten_inside_job_parameters(tmp_path) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    rows = [{"x": 1}]
    path = tmp_path / "jobs.sqlite"
    service = DurableExecutionService(SqliteJobStore(path, migration_now=_MIGRATION_NOW))
    coordinator = LocalExecutionCoordinator(
        runner=SimpleNamespace(), store=JobStoreExecutionStore(service), autostart=False
    )
    try:
        coordinator.submit("workspace-a", "job-parameters-tampered", lab, rows)
        adapter = coordinator._store
        assert isinstance(adapter, JobStoreExecutionStore)
        job_id, _ = adapter._ids("workspace-a", "job-parameters-tampered")
        job = asyncio.run(service.status(job_id))
        assert job is not None
        parameters = decode_canonical_json(job.parameters_json)
        assert isinstance(parameters, dict)
        pipeline = PipelineIR.from_json(parameters["pipeline_json"])
        changed_pipeline = PipelineIR(
            nodes=pipeline.nodes,
            parameters=tuple(
                (name, "forged" if name == "seed" else value) for name, value in pipeline.parameters
            ),
        )
        parameters["pipeline_json"] = changed_pipeline.to_json()
        parameters["pipeline_digest"] = changed_pipeline.digest
        parameters["request_digest"] = hashlib.sha256(
            encode_canonical_json(
                {"lab": lab.to_payload(), "pipeline": changed_pipeline.to_payload(), "rows": rows}
            )
        ).hexdigest()
        with sqlite3.connect(path) as connection:
            connection.execute(
                "UPDATE jobs SET parameters_json=? WHERE job_id=?",
                (encode_canonical_json(parameters).decode("utf-8"), str(job_id)),
            )

        claim = adapter.claim_next("tamper-check")
        assert claim is not None
        assert claim.input_error == (
            "stored ML request digest does not match the durable Job identity"
        )
        adapter.finish_claim(claim, state="failed", error=claim.input_error)
    finally:
        coordinator.close()
        asyncio.run(service.aclose())


def test_worker_rejects_pipeline_snapshot_tampering_before_runner() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )

    class MustNotRun:
        called = False

        def run(self, _lab, _rows):
            self.called = True
            raise AssertionError("runner must not receive a tampered pipeline")

    runner = MustNotRun()
    coordinator = LocalExecutionCoordinator(runner=runner, autostart=False)
    try:
        coordinator.submit("workspace-a", "pipeline-tampered", lab, [{"x": 1}])
        key = ("workspace-a", "pipeline-tampered")
        stored = coordinator._store._items[key]
        pipeline = PipelineIR.from_json(stored.pipeline_json or "")
        changed = PipelineIR(
            nodes=pipeline.nodes,
            parameters=tuple(
                (name, "tampered" if name == "seed" else value)
                for name, value in pipeline.parameters
            ),
        )
        coordinator._store._items[key] = replace(stored, pipeline_json=changed.to_json())
        coordinator.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            result = coordinator.status(*key)
            if result.state in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert result.state == "failed"
        assert "pipeline" in (result.error or "").lower()
        assert runner.called is False
    finally:
        coordinator.close()


def test_local_coordinator_rejects_oversized_requests_before_persisting(monkeypatch) -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    monkeypatch.setattr("studio_ml.orchestration.MAX_EXECUTION_REQUEST_BYTES", 64)
    coordinator = LocalExecutionCoordinator()
    try:
        with pytest.raises(ValueError, match="exceeds 64 bytes"):
            coordinator.submit("ws", "oversized", lab, [{"x": "value" * 20}])
        assert coordinator._store.get("ws", "oversized") is None
    finally:
        coordinator.close()


def test_expired_execution_owner_is_fenced_from_late_completion() -> None:
    store = InMemoryExecutionStore()
    snapshot = ExecutionSnapshot(
        "fenced-run",
        "queued",
        workspace_id="ws",
        lab_id="lab",
        lab_digest="a" * 64,
        request_digest="b" * 64,
        lab_json="{}",
        rows_json="[]",
    )
    store.create(snapshot)
    first = store.claim(
        "ws",
        "fenced-run",
        "owner-1",
        now=Instant("2026-10-19T00:00:00.000000Z"),
        lease_until=Instant("2026-10-19T00:01:00.000000Z"),
    )
    assert first is not None
    second = store.claim(
        "ws",
        "fenced-run",
        "owner-2",
        now=Instant("2026-10-19T00:01:01.000000Z"),
        lease_until=Instant("2026-10-19T00:02:01.000000Z"),
    )
    assert second is not None
    assert second.fence > first.fence
    assert store.finish("ws", "fenced-run", "owner-1", first.fence, state="succeeded") is None
    assert store.finish("ws", "fenced-run", "owner-2", second.fence, state="succeeded") is not None


def test_local_coordinator_executes_clustering_lab() -> None:
    lab = Lab(
        id="clusters",
        name="Clusters",
        project_id="project",
        dataset=AssetRef(AssetId("asset"), AssetVersion("v1")),
        target=None,
        task="clustering",
        features=(FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit(
            "ws", "cluster-run", lab, [{"x": value} for value in (0.0, 0.1, 9.9, 10.0)]
        )
        for _ in range(100):
            snapshot = coordinator.status("ws", "cluster-run")
            if snapshot.state == "succeeded":
                assert snapshot.result_payload is not None
                assert snapshot.result_payload["algorithm"] == "kmeans"
                return
            if snapshot.state == "failed":
                raise AssertionError(snapshot.error)
            import time

            time.sleep(0.01)
        raise AssertionError("clustering execution did not finish")
    finally:
        coordinator.close()


def test_local_coordinator_cancel_does_not_deadlock() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    coordinator = LocalExecutionCoordinator()
    try:
        coordinator.submit(
            "ws", "run-cancel", lab, [{"x": n, "target": n % 2} for n in range(1, 21)]
        )
        outcome: list[object] = []

        def cancel() -> None:
            try:
                outcome.append(coordinator.cancel("ws", "run-cancel"))
            except Exception as exc:  # pragma: no cover - surfaced by the assertion below
                outcome.append(exc)

        thread = Thread(target=cancel, daemon=True)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "cancel deadlocked while reading its own status"
        assert len(outcome) == 1
        assert not isinstance(outcome[0], Exception), outcome[0]
        assert coordinator.status("ws", "run-cancel").state in {
            "cancelled",
            "succeeded",
            "failed",
        }
    finally:
        coordinator.close()


def test_cancel_remains_terminal_when_runner_fails_after_cancellation() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    started = Event()
    release_failure = Event()

    class FailingRunner:
        def run(self, _lab, _rows):
            started.set()
            if not release_failure.wait(timeout=5):
                raise TimeoutError("test runner was not released")
            raise ValueError("runner failed after cancellation")

    store = InMemoryExecutionStore()
    coordinator = LocalExecutionCoordinator(runner=FailingRunner(), store=store)
    try:
        coordinator.submit("ws", "run-cancel-race", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "runner did not start"

        cancelled = coordinator.cancel("ws", "run-cancel-race")
        assert cancelled.state == "cancelled"

        future = _active_future(coordinator, ("ws", "run-cancel-race"))
        release_failure.set()
        with pytest.raises(ValueError, match="runner failed after cancellation"):
            future.result(timeout=5)

        assert coordinator.status("ws", "run-cancel-race").state == "cancelled"
        persisted = store.get("ws", "run-cancel-race")
        assert persisted is not None
        assert persisted.state == "cancelled"
    finally:
        release_failure.set()
        coordinator.close()


def test_cancelled_running_run_does_not_become_succeeded_on_late_success() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    started = Event()
    release_success = Event()

    class BlockingRunner:
        def run(self, _lab, _rows):
            started.set()
            if not release_success.wait(timeout=5):
                raise TimeoutError("test runner was not released")
            return SimpleNamespace(to_payload=lambda: {"status": "completed"})

    store = InMemoryExecutionStore()
    coordinator = LocalExecutionCoordinator(runner=BlockingRunner(), store=store)
    try:
        coordinator.submit("ws", "run-cancel-success", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "runner did not start"
        assert coordinator.cancel("ws", "run-cancel-success").state == "cancelled"

        future = _active_future(coordinator, ("ws", "run-cancel-success"))
        release_success.set()
        future.result(timeout=5)

        assert coordinator.status("ws", "run-cancel-success").state == "cancelled"
        persisted = store.get("ws", "run-cancel-success")
        assert persisted is not None
        assert persisted.state == "cancelled"
    finally:
        release_success.set()
        coordinator.close()


def test_cancel_prevents_a_queued_run_from_starting() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    started = Event()
    release = Event()
    calls: list[int] = []

    class BlockingRunner:
        def run(self, _lab, _rows):
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                started.set()
                if not release.wait(timeout=5):
                    raise TimeoutError("test runner was not released")
            return SimpleNamespace(to_payload=lambda: {"calls": len(calls)})

    coordinator = LocalExecutionCoordinator(runner=BlockingRunner(), max_workers=1)
    try:
        coordinator.submit("ws", "run-active", lab, [{"x": 1, "target": 1}])
        assert started.wait(timeout=5), "first runner did not start"
        active_future = _active_future(coordinator, ("ws", "run-active"))

        coordinator.submit("ws", "run-queued", lab, [{"x": 2, "target": 0}])
        assert coordinator.status("ws", "run-queued").state == "queued"
        assert ("ws", "run-queued") not in coordinator._futures
        assert coordinator.cancel("ws", "run-queued").state == "cancelled"

        release.set()
        active_future.result(timeout=5)

        assert calls == [1]
        assert coordinator.status("ws", "run-queued").state == "cancelled"
    finally:
        release.set()
        coordinator.close()
