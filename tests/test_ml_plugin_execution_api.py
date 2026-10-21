"""Async execution route contract tests."""

# ruff: noqa: E501
import json
import time
from threading import Event

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_core.ml import RegisteredModelVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import ExecutionSnapshot, LocalExecutionCoordinator
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.runner import LocalExperimentRunner
from studio_ml.services import InMemoryMLLabStore, LabService
from studio_storage import LocalArtifactStore


def test_submit_and_poll_execution() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    with pytest.raises(ValueError, match="preprocessor is not supported"):
        plugin.submit_execution(
            "ws",
            "churn",
            body={"run_id": "unsupported-preprocessor", "preprocessor": "custom"},
        )
    submitted = plugin.submit_execution(
        "ws",
        "churn",
        body={
            "run_id": "async-1",
            "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
            "algorithm": "decision_tree_classifier",
            "preprocessor": "standard_scale",
        },
    )
    assert submitted["run_id"] == "async-1"
    deadline = time.time() + 30
    state = plugin.execution_status("async-1", workspace_id="ws")["state"]
    while state not in {"succeeded", "failed"} and time.time() < deadline:
        time.sleep(0.01)
        state = plugin.execution_status("async-1", workspace_id="ws")["state"]
    assert state == "succeeded"
    assert (
        plugin.execution_status("async-1", workspace_id="ws")["result"]["algorithm"]
        == "decision_tree_classifier"
    )
    plugin._coordinator.close()


def test_submit_candidate_algorithms_runs_and_pins_v2_pipeline() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x", "numeric"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    try:
        submitted = plugin.submit_execution(
            "ws",
            "churn",
            body={
                "run_id": "candidate-run",
                "rows": rows,
                "candidate_algorithms": ["logistic_regression", "decision_tree_classifier"],
                "selection_metric": "accuracy",
            },
        )
        assert submitted["run_id"] == "candidate-run"
        pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert pipeline is not None
        assert pipeline.schema == "ronin.ml-pipeline-ir/v2"
        deadline = time.time() + 30
        state = plugin.execution_status("candidate-run", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("candidate-run", workspace_id="ws")["state"]
        assert state == "succeeded"
        assert plugin.execution_status("candidate-run", workspace_id="ws")["result"][
            "algorithm"
        ] in {
            "logistic_regression",
            "decision_tree_classifier",
        }
    finally:
        plugin._coordinator.close()


def test_submit_one_hot_execution_uses_categorical_lab_feature() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("segment", "categorical"), FeatureSpec("age", "numeric")),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    rows = [
        {"segment": "blue" if index % 2 else "red", "age": float(index), "target": index % 2}
        for index in range(20)
    ]
    try:
        plugin.submit_execution(
            "ws",
            lab.id,
            body={"run_id": "one-hot-run", "rows": rows, "preprocessor": "one_hot"},
        )
        deadline = time.time() + 30
        state = plugin.execution_status("one-hot-run", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("one-hot-run", workspace_id="ws")["state"]
        assert state == "succeeded"
        assert plugin.execution_status("one-hot-run", workspace_id="ws")["result"]["algorithm"]
    finally:
        plugin._coordinator.close()


def test_submit_median_impute_execution_fills_null_and_blank_numeric_values() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "missing",
        "Missing values",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("age", "numeric"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    rows = [
        {"age": None if index == 0 else ("" if index == 1 else float(index)), "target": index % 2}
        for index in range(20)
    ]
    try:
        plugin.submit_execution(
            "ws",
            lab.id,
            body={"run_id": "median-impute-run", "rows": rows, "preprocessor": "median_impute"},
        )
        deadline = time.time() + 30
        state = plugin.execution_status("median-impute-run", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("median-impute-run", workspace_id="ws")["state"]
        assert state == "succeeded"
        assert plugin.execution_status("median-impute-run", workspace_id="ws")["result"]
    finally:
        plugin._coordinator.close()


def test_submit_composed_preprocessing_accepts_mixed_lab_features() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "mixed",
        "Mixed features",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("segment", "categorical"), FeatureSpec("age", "numeric")),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    rows = [
        {
            "segment": "blue" if index % 2 else "red",
            "age": None if index == 0 else float(index),
            "target": index % 2,
        }
        for index in range(20)
    ]
    try:
        plugin.submit_execution(
            "ws",
            lab.id,
            body={
                "run_id": "composed-preprocessing-run",
                "rows": rows,
                "preprocessor": "one_hot_median_impute",
            },
        )
        deadline = time.time() + 30
        state = plugin.execution_status("composed-preprocessing-run", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("composed-preprocessing-run", workspace_id="ws")[
                "state"
            ]
        assert state == "succeeded"
    finally:
        plugin._coordinator.close()


def test_submit_rejects_run_ids_longer_than_public_limit() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    try:
        with pytest.raises(ValueError, match="1 to 256 characters"):
            plugin.submit_execution("ws", "churn", body={"run_id": "x" * 257, "rows": []})
    finally:
        plugin._coordinator.close()


def test_custom_algorithm_fails_closed_for_runner_without_pipeline_support() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._coordinator.close()
    called = False

    class LegacyRunner:
        def run(self, *_args):
            nonlocal called
            called = True
            raise AssertionError("custom PipelineIR must not be ignored")

    plugin._coordinator = LocalExecutionCoordinator(runner=LegacyRunner())
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    try:
        plugin.submit_execution(
            "ws",
            "churn",
            body={
                "run_id": "legacy-custom-pipeline",
                "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
                "algorithm": "decision_tree_classifier",
            },
        )
        deadline = time.time() + 5
        state = plugin.execution_status("legacy-custom-pipeline", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("legacy-custom-pipeline", workspace_id="ws")["state"]
        assert state == "failed"
        assert called is False
    finally:
        plugin._coordinator.close()


def test_cancel_execution_route_keeps_cancelled_state_after_runner_error() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._coordinator.close()
    started = Event()
    release_failure = Event()

    class FailingRunner:
        def run(self, _lab, _rows):
            started.set()
            if not release_failure.wait(timeout=5):
                raise TimeoutError("test runner was not released")
            raise ValueError("runner failed after cancellation")

    plugin._coordinator = LocalExecutionCoordinator(runner=FailingRunner())
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    try:
        plugin.submit_execution(
            "ws", "churn", body={"run_id": "cancel-api", "rows": [{"x": 1, "target": 1}]}
        )
        assert started.wait(timeout=5), "runner did not start"
        assert plugin.cancel_execution("cancel-api", workspace_id="ws")["state"] == "cancelled"

        deadline = time.monotonic() + 5
        while (
            "ws",
            "cancel-api",
        ) not in plugin._coordinator._futures and time.monotonic() < deadline:
            time.sleep(0.001)
        future = plugin._coordinator._futures[("ws", "cancel-api")]
        release_failure.set()
        with pytest.raises(ValueError, match="runner failed after cancellation"):
            future.result(timeout=5)
        assert plugin.execution_status("cancel-api", workspace_id="ws")["state"] == "cancelled"
    finally:
        release_failure.set()
        plugin._coordinator.close()


def test_register_execution_model_persists_run_and_verified_artifact(tmp_path) -> None:
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
    result = LocalExperimentRunner().run(lab, rows)
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    artifact = artifacts.put_bytes(
        role="model",
        data=result.model.artifact_bytes,
        media_type="application/vnd.ronin.sklearn-tabular+json",
    )

    class Registry:
        def __init__(self):
            self.experiments = []
            self.runs = []
            self.models = []

        def put_experiment(self, _workspace, experiment, *, now):
            self.experiments.append((experiment, now))
            return experiment

        def record_run(self, _workspace, run, *, now):
            self.runs.append((run, now))
            return run

        def register_model(self, _workspace, model, *, now):
            self.models.append((model, now))
            return model

    registry = Registry()
    plugin = MachineLearningStudioPlugin()
    plugin._coordinator.close()
    plugin._coordinator = type(
        "CompletedCoordinator",
        (),
        {
            "close": lambda _self: None,
            "status": lambda _self, _workspace, _run: ExecutionSnapshot(
                run_id="run-1",
                state="succeeded",
                workspace_id="ws",
                lab_id=lab.id,
                lab_digest=lab.digest,
                rows_json=json.dumps(rows),
                result_payload={
                    "lab_id": lab.id,
                    "task": result.model.task,
                    "algorithm": result.model.algorithm,
                    "backend_id": result.backend_id,
                    "features": list(result.model.features),
                    "target": result.model.target,
                    "metrics": [[name, value] for name, value in result.model.metrics],
                    "artifact_ref": artifact.storage_ref,
                    "artifact_digest": artifact.digest,
                    "artifact_media_type": artifact.media_type,
                    "artifact_size_bytes": artifact.size_bytes,
                },
            ),
        },
    )()
    plugin._labs = LabService(InMemoryMLLabStore())
    plugin._labs.create(WorkspaceId("ws"), lab)
    plugin._registry = registry
    plugin._artifacts = artifacts
    try:
        model = plugin.register_execution_model(
            "run-1", workspace_id="ws", body={"model_id": "churn", "version": "v1"}
        )
        assert model["artifact_ref"] == artifact.storage_ref
        assert model["source_run_id"] == "run-1"
        assert model["signature"]["inputs"] == {"x": "int64"}
        assert registry.runs[0][0].artifact_refs == (artifact.storage_ref,)
        assert isinstance(registry.models[0][0], RegisteredModelVersion)
    finally:
        plugin._coordinator.close()


def test_register_execution_model_rejects_unfinished_execution() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._coordinator.close()
    plugin._registry = object()
    plugin._artifacts = object()
    plugin._labs = object()
    plugin._coordinator = type(
        "QueuedCoordinator",
        (),
        {
            "close": lambda _self: None,
            "status": lambda *_args: ExecutionSnapshot(run_id="queued", state="running"),
        },
    )()
    try:
        with pytest.raises(ValueError, match="only a succeeded execution"):
            plugin.register_execution_model(
                "queued", workspace_id="ws", body={"model_id": "m", "version": "v1"}
            )
    finally:
        plugin._coordinator.close()


def test_quality_route_returns_blocking_findings() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "quality",
        "Quality",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    report = plugin.quality_check("ws", "quality", body={"rows": [{"x": 1, "target": "only"}] * 3})
    assert report["passed"] is False
    assert report["failures"]
    plugin._coordinator.close()


def test_compare_route_ranks_trials_deterministically() -> None:
    plugin = MachineLearningStudioPlugin()
    result = plugin.compare_trials(
        "ws",
        "lab",
        body={
            "spec": {"mode": "grid", "metric": "accuracy", "direction": "maximize"},
            "trials": [
                {"parameters": {"C": 1}, "metrics": {"accuracy": 0.8}},
                {"parameters": {"C": 2}, "metrics": {"accuracy": 0.9}},
            ],
        },
    )
    assert result["items"][0]["metrics"]["accuracy"] == 0.9
    plugin._coordinator.close()


def test_search_route_executes_grid_trials() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search",
        "Search",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    result = plugin.search_trials(
        "ws",
        "search",
        body={
            "spec": {
                "mode": "grid",
                "parameters": [{"name": "seed", "values": [1, 2]}],
                "metric": "accuracy",
            },
            "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
        },
    )
    assert len(result["items"]) == 2
    assert all("metrics" in item for item in result["items"])
    plugin._coordinator.close()


def test_search_registration_requires_persistent_services() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search-register",
        "Search",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    with pytest.raises(ValueError, match="artifact_store"):
        plugin.search_trials(
            "ws",
            "search-register",
            body={
                "spec": {"mode": "single"},
                "register": {"model_id": "churn"},
                "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
            },
        )
    plugin._coordinator.close()


def test_batch_prediction_evidence_binds_input_and_replay_identity() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin.predict_model = lambda *_args, **_kwargs: {"predictions": [1, 0]}  # type: ignore[method-assign]
    result = plugin.batch_predict_model(
        "ws",
        "model",
        "v1",
        body={"batch_id": "batch-1", "rows": [{"x": 1}, {"x": 2}]},
    )
    assert result["row_count"] == 2
    evidence = result["evidence"]
    assert evidence["replay_key"] == "model@v1:batch-1"  # type: ignore[index]
    assert len(evidence["input_sha256"]) == 64  # type: ignore[index]


def test_batch_prediction_rejects_empty_or_non_object_rows() -> None:
    plugin = MachineLearningStudioPlugin()
    with pytest.raises(ValueError, match="at most 100000"):
        plugin.batch_predict_model("ws", "model", "v1", body={"batch_id": "b", "rows": []})
    with pytest.raises(ValueError, match="at most 100000"):
        plugin.batch_predict_model(
            "ws", "model", "v1", body={"batch_id": "b", "rows": ["not-an-object"]}
        )
