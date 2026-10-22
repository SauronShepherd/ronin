"""Async execution route contract tests."""

# ruff: noqa: E501
import json
import time
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_core.ml import RegisteredModelVersion
from studio_execution import DurableExecutionService
from studio_ml.domain import (
    PIPELINE_SCHEMA_V2,
    PIPELINE_SCHEMA_V3,
    FeatureSpec,
    Lab,
    PipelineIR,
    PipelineNode,
)
from studio_ml.orchestration import (
    ExecutionSnapshot,
    JobStoreExecutionStore,
    LocalExecutionCoordinator,
)
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.runner import LocalExperimentRunner
from studio_ml.services import InMemoryMLLabStore, LabService, compile_lab_pipeline
from studio_orchestrator import Instant
from studio_storage import LocalArtifactStore, SqliteJobStore


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


def test_pipeline_register_executes_durably_and_persists_registered_model(tmp_path) -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._coordinator.close()
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

    class Registry:
        def __init__(self):
            self.experiments = {}
            self.runs = {}
            self.models = {}

        def put_experiment(self, _workspace, experiment, *, now):
            del now
            self.experiments[experiment.id.value] = experiment
            return experiment

        def record_run(self, _workspace, run, *, now):
            del now
            self.runs[run.id.value] = run
            return run

        def get_model(self, _workspace, model_id, version):
            return self.models.get((model_id.value, version.value))

        def register_model(self, _workspace, model, *, now):
            del now
            key = (model.model_id.value, model.version.value)
            existing = self.models.setdefault(key, model)
            if existing != model:
                raise ValueError("registered model version conflicts")
            return existing

    registry = Registry()
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    jobs = SqliteJobStore(
        tmp_path / "jobs.sqlite", migration_now=Instant("2026-10-19T00:00:00.000000Z")
    )
    service = DurableExecutionService(jobs)
    plugin._registry = registry
    plugin._artifacts = artifacts
    plugin._coordinator = LocalExecutionCoordinator(
        runner=LocalExperimentRunner(),
        store=JobStoreExecutionStore(service, artifacts),
        autostart=True,
        result_finalizer=plugin._finalize_pipeline_registration,
    )
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    try:
        submitted = plugin.submit_execution(
            "ws",
            "churn",
            body={
                "run_id": "register-api",
                "rows": rows,
                "register": {"model_id": "churn", "version": "candidate-1"},
            },
        )
        assert submitted["run_id"] == "register-api"
        pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert pipeline is not None
        assert pipeline.schema == PIPELINE_SCHEMA_V2
        assert pipeline.nodes[-1].kind == "register"
        deadline = time.time() + 30
        status = plugin.execution_status("register-api", workspace_id="ws")
        while status["state"] not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            status = plugin.execution_status("register-api", workspace_id="ws")
        assert status["state"] == "succeeded", status.get("error")
        result = status["result"]
        assert isinstance(result, dict)
        assert result["registered_model"]["model_id"] == "churn"
        assert result["registered_model"]["version"] == "candidate-1"
        assert len(registry.runs) == 1
        assert len(registry.models) == 1
        v3 = PipelineIR(
            (
                PipelineNode("p", "profile"),
                PipelineNode("q", "quality_gate", inputs=(("profile", ("p.out",)),)),
                PipelineNode("prep", "prepare", inputs=(("quality", ("q.out",)),)),
                PipelineNode(
                    "train",
                    "train",
                    config={"algorithm": "logistic_regression"},
                    inputs=(("prepared", ("prep.out",)),),
                ),
                PipelineNode("eval", "evaluate", inputs=(("model", ("train.out",)),)),
                PipelineNode("select", "select", inputs=(("candidates", ("eval.out",)),)),
                PipelineNode(
                    "register",
                    "register",
                    config={"model_id": "churn", "version": "candidate-2"},
                    inputs=(("selected", ("select.out",)),),
                ),
            ),
            parameters=compile_lab_pipeline(lab).parameters,
            schema=PIPELINE_SCHEMA_V3,
        )
        submitted_v3 = plugin.submit_execution(
            "ws",
            "churn",
            body={"run_id": "register-v3-api", "rows": rows, "pipeline": v3.to_payload()},
        )
        assert submitted_v3["run_id"] == "register-v3-api"
        deadline = time.time() + 30
        v3_status = plugin.execution_status("register-v3-api", workspace_id="ws")
        while v3_status["state"] not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            v3_status = plugin.execution_status("register-v3-api", workspace_id="ws")
        assert v3_status["state"] == "succeeded", v3_status.get("error")
        assert v3_status["result"]["registered_model"]["version"] == "candidate-2"
        assert len(registry.models) == 2
        persisted_snapshot = ExecutionSnapshot(
            run_id="register-api",
            state="succeeded",
            workspace_id="ws",
            lab_id=lab.id,
            lab_digest=lab.digest,
            pipeline_digest=pipeline.digest,
            request_digest="test-request",
            pipeline_json=pipeline.to_json(),
            rows_json=json.dumps(rows),
        )
        repeated = plugin._finalize_pipeline_registration(
            persisted_snapshot,
            {key: value for key, value in result.items() if key != "registered_model"},
        )
        assert repeated["registered_model"] == result["registered_model"]
        assert len(registry.runs) == 2
        assert len(registry.models) == 2
        replayed_retry = plugin._finalize_pipeline_registration(
            replace(persisted_snapshot, run_id="register-api-retry"),
            {key: value for key, value in result.items() if key != "registered_model"},
        )
        assert replayed_retry["registered_model"] == result["registered_model"]
        assert len(registry.runs) == 2
        assert len(registry.models) == 2
        registered_bytes = artifacts.get_bytes_by_storage_ref(
            result["artifact_ref"],
            digest=result["artifact_digest"].removeprefix("sha256:"),
        )
        assert len(registered_bytes) == result["artifact_size_bytes"]
    finally:
        plugin._coordinator.close()
        import asyncio

        asyncio.run(service.aclose())


def test_submit_candidate_preprocessors_executes_each_bound_branch() -> None:
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
                "run_id": "preprocessor-candidates",
                "rows": rows,
                "algorithm": "decision_tree_classifier",
                "candidate_preprocessors": ["identity", "standard_scale"],
            },
        )
        assert submitted["run_id"] == "preprocessor-candidates"
        pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert pipeline is not None
        prepares = [node for node in pipeline.nodes if node.kind == "prepare"]
        trains = [node for node in pipeline.nodes if node.kind == "train"]
        assert [node.config["preprocessor"] for node in prepares] == [
            "identity",
            "standard_scale",
        ]
        assert [node.depends_on for node in trains] == [(node.id,) for node in prepares]
        deadline = time.time() + 30
        state = plugin.execution_status("preprocessor-candidates", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("preprocessor-candidates", workspace_id="ws")["state"]
        assert state == "succeeded"
        assert (
            plugin.execution_status("preprocessor-candidates", workspace_id="ws")["result"][
                "algorithm"
            ]
            == "decision_tree_classifier"
        )
    finally:
        plugin._coordinator.close()


def test_submit_candidate_grid_crosses_algorithms_and_preprocessors() -> None:
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
                "run_id": "candidate-grid",
                "rows": rows,
                "candidate_algorithms": ["logistic_regression", "decision_tree_classifier"],
                "candidate_preprocessors": ["identity", "standard_scale"],
            },
        )
        assert submitted["run_id"] == "candidate-grid"
        pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert pipeline is not None
        prepares = [node for node in pipeline.nodes if node.kind == "prepare"]
        trains = [node for node in pipeline.nodes if node.kind == "train"]
        assert len(prepares) == 2
        assert len(trains) == 4
        assert {node.config["algorithm"] for node in trains} == {
            "logistic_regression",
            "decision_tree_classifier",
        }
        assert {node.depends_on[0] for node in trains} == {node.id for node in prepares}
        deadline = time.time() + 30
        state = plugin.execution_status("candidate-grid", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("candidate-grid", workspace_id="ws")["state"]
        assert state == "succeeded"
    finally:
        plugin._coordinator.close()


def test_submit_custom_v2_pipeline_is_validated_and_pinned() -> None:
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
    compiled = compile_lab_pipeline(
        lab, candidate_algorithms=("logistic_regression", "decision_tree_classifier")
    )
    id_map = {node.id: f"custom_{node.id}" for node in compiled.nodes}
    custom = PipelineIR(
        tuple(
            PipelineNode(
                id_map[node.id],
                node.kind,
                tuple(id_map[dependency] for dependency in node.depends_on),
                node.config,
            )
            for node in reversed(compiled.nodes)
        ),
        compiled.parameters,
        compiled.schema,
    )
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    try:
        submitted = plugin.submit_execution(
            "ws",
            lab.id,
            body={"run_id": "custom-pipeline-run", "rows": rows, "pipeline": custom.to_payload()},
        )
        assert submitted["run_id"] == "custom-pipeline-run"
        stored_pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert stored_pipeline == custom
        deadline = time.time() + 30
        state = plugin.execution_status("custom-pipeline-run", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("custom-pipeline-run", workspace_id="ws")["state"]
        assert state == "succeeded"
    finally:
        plugin._coordinator.close()


def test_submit_custom_v3_typed_dag_is_validated_and_pinned() -> None:
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
    compiled = compile_lab_pipeline(lab)
    custom = PipelineIR(
        (
            PipelineNode("profile", "profile"),
            PipelineNode("quality", "quality_gate", inputs=(("profile", ("profile.out",)),)),
            PipelineNode("prepare_a", "prepare", inputs=(("quality", ("quality.out",)),)),
            PipelineNode(
                "prepare_b",
                "prepare",
                config={"preprocessor": "standard_scale"},
                inputs=(("quality", ("quality.out",)),),
            ),
            PipelineNode(
                "train_a",
                "train",
                config={"algorithm": "logistic_regression"},
                inputs=(("prepared", ("prepare_a.out",)),),
            ),
            PipelineNode(
                "train_b",
                "train",
                config={"algorithm": "decision_tree_classifier"},
                inputs=(("prepared", ("prepare_b.out",)),),
            ),
            PipelineNode("eval_a", "evaluate", inputs=(("model", ("train_a.out",)),)),
            PipelineNode("eval_b", "evaluate", inputs=(("model", ("train_b.out",)),)),
            PipelineNode(
                "select",
                "select",
                config={"metric": "accuracy"},
                inputs=(("candidates", ("eval_a.out", "eval_b.out")),),
            ),
        ),
        parameters=compiled.parameters,
        schema=PIPELINE_SCHEMA_V3,
    )
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    try:
        submitted = plugin.submit_execution(
            "ws",
            lab.id,
            body={"run_id": "custom-v3-run", "rows": rows, "pipeline": custom.to_payload()},
        )
        assert submitted["run_id"] == "custom-v3-run"
        stored_pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert stored_pipeline is not None
        assert stored_pipeline.schema == PIPELINE_SCHEMA_V3
        assert dict(stored_pipeline.parameters)["stage_registry_digest"]
        deadline = time.time() + 30
        status = plugin.execution_status("custom-v3-run", workspace_id="ws")
        while status["state"] not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            status = plugin.execution_status("custom-v3-run", workspace_id="ws")
        assert status["state"] == "succeeded"
        assert {stage["id"] for stage in status["pipeline_stages"]} == {
            "profile",
            "quality",
            "prepare_a",
            "prepare_b",
            "train_a",
            "train_b",
            "eval_a",
            "eval_b",
            "select",
        }
        assert status["result"]["algorithm"] in {
            "logistic_regression",
            "decision_tree_classifier",
        }
        invalid_nodes = tuple(
            PipelineNode(
                node.id,
                node.kind,
                config={"algorithm": "decision_tree_regressor"}
                if node.id == "train_a"
                else node.config,
                inputs=node.inputs,
                stage_version=node.stage_version,
            )
            for node in custom.nodes
        )
        invalid = PipelineIR(invalid_nodes, custom.parameters, PIPELINE_SCHEMA_V3)
        with pytest.raises(ValueError, match="not supported for this Lab"):
            plugin.submit_execution(
                "ws",
                lab.id,
                body={
                    "run_id": "invalid-v3-task",
                    "rows": rows,
                    "pipeline": invalid.to_payload(),
                },
            )
        with pytest.raises(KeyError):
            plugin.execution_status("invalid-v3-task", workspace_id="ws")
    finally:
        plugin._coordinator.close()


def test_custom_v2_pipeline_with_register_stage_is_rejected_before_job_creation() -> None:
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
    compiled = compile_lab_pipeline(
        lab, candidate_algorithms=("logistic_regression", "decision_tree_classifier")
    )
    mismatched_parameters = tuple(
        (key, "sha256:wrong-lab" if key == "lab_digest" else value)
        for key, value in compiled.parameters
    )
    mismatched = PipelineIR(compiled.nodes, mismatched_parameters, compiled.schema)
    unsupported = PipelineIR(
        tuple(
            PipelineNode(
                node.id,
                "register" if node.kind == "quality_gate" else node.kind,
                node.depends_on,
                node.config,
            )
            for node in compiled.nodes
        ),
        compiled.parameters,
        compiled.schema,
    )
    unsupported_algorithm = PipelineIR(
        tuple(
            PipelineNode(
                node.id,
                node.kind,
                node.depends_on,
                {"algorithm": "untrusted_algorithm"} if node.kind == "train" else node.config,
            )
            for node in compiled.nodes
        ),
        compiled.parameters,
        compiled.schema,
    )
    try:
        with pytest.raises(ValueError, match="parameters do not match the submitted Lab"):
            plugin.submit_execution(
                "ws",
                lab.id,
                body={
                    "run_id": "mismatched-pipeline",
                    "rows": [{"x": value, "target": value % 2} for value in range(1, 21)],
                    "pipeline": mismatched.to_payload(),
                },
            )
        with pytest.raises(KeyError):
            plugin.execution_status("mismatched-pipeline", workspace_id="ws")
        with pytest.raises(ValueError, match="shared stages, paired candidates"):
            plugin.submit_execution(
                "ws",
                lab.id,
                body={
                    "run_id": "rejected-register-pipeline",
                    "rows": [{"x": value, "target": value % 2} for value in range(1, 21)],
                    "pipeline": unsupported.to_payload(),
                },
            )
        with pytest.raises(KeyError):
            plugin.execution_status("rejected-register-pipeline", workspace_id="ws")
        with pytest.raises(ValueError, match="not supported for this Lab task"):
            plugin.submit_execution(
                "ws",
                lab.id,
                body={
                    "run_id": "rejected-algorithm-pipeline",
                    "rows": [{"x": value, "target": value % 2} for value in range(1, 21)],
                    "pipeline": unsupported_algorithm.to_payload(),
                },
            )
        with pytest.raises(KeyError):
            plugin.execution_status("rejected-algorithm-pipeline", workspace_id="ws")
    finally:
        plugin._coordinator.close()


def test_custom_pipeline_fails_before_job_when_runner_cannot_validate_it() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._coordinator.close()

    class LegacyRunner:
        def run(self, *_args):
            raise AssertionError("custom pipeline must not reach a legacy runner")

    plugin._coordinator = LocalExecutionCoordinator(runner=LegacyRunner())
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
    pipeline = compile_lab_pipeline(
        lab, candidate_algorithms=("logistic_regression", "decision_tree_classifier")
    )
    try:
        with pytest.raises(ValueError, match="cannot validate custom ML pipelines"):
            plugin.submit_execution(
                "ws",
                lab.id,
                body={
                    "run_id": "legacy-custom-pipeline",
                    "rows": [{"x": value, "target": value % 2} for value in range(1, 21)],
                    "pipeline": pipeline.to_payload(),
                },
            )
        with pytest.raises(KeyError):
            plugin.execution_status("legacy-custom-pipeline", workspace_id="ws")
    finally:
        plugin._coordinator.close()


def test_submit_clustering_candidates_runs_and_pins_v2_pipeline() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        None,
        "clustering",
        (FeatureSpec("x", "numeric"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    try:
        submitted = plugin.submit_execution(
            "ws",
            lab.id,
            body={
                "run_id": "cluster-candidate-run",
                "rows": [{"x": value} for value in range(1, 21)],
                "candidate_cluster_counts": [2, 3, 4],
            },
        )
        assert submitted["run_id"] == "cluster-candidate-run"
        pipeline = plugin._labs.store.get_pipeline(WorkspaceId("ws"), lab.id)
        assert pipeline is not None
        assert pipeline.schema == "ronin.ml-pipeline-ir/v2"
        deadline = time.time() + 30
        state = plugin.execution_status("cluster-candidate-run", workspace_id="ws")["state"]
        while state not in {"succeeded", "failed"} and time.time() < deadline:
            time.sleep(0.01)
            state = plugin.execution_status("cluster-candidate-run", workspace_id="ws")["state"]
        assert state == "succeeded"
        result = plugin.execution_status("cluster-candidate-run", workspace_id="ws")["result"]
        assert result["task"] == "clustering"
        assert result["selection_metric"] == "calinski_harabasz"
        assert result["selection_score"] > 0
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

        def get_model(self, _workspace, _model_id, _version):
            return None

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
            "spec": {
                "mode": "grid",
                "metric": "accuracy",
                "direction": "maximize",
                "tie_breakers": [{"metric": "cost", "direction": "minimize"}],
            },
            "trials": [
                {"parameters": {"C": 1}, "metrics": {"accuracy": 0.9, "cost": 2}},
                {"parameters": {"C": 2}, "metrics": {"accuracy": 0.9, "cost": 1}},
                {"parameters": {"C": 3}, "metrics": {"accuracy": 0.8, "cost": 0}},
            ],
        },
    )
    assert result["items"][0]["parameters"]["C"] == 2
    assert result["tie_breakers"] == [{"metric": "cost", "direction": "minimize"}]
    plugin._coordinator.close()


@pytest.mark.parametrize(
    "tie_breakers",
    [
        [{"metric": "cost", "direction": "minimize", "unexpected": True}],
        [{"metric": f"metric-{index}", "direction": "maximize"} for index in range(9)],
    ],
)
def test_compare_route_rejects_invalid_tie_breaker_contract(
    tie_breakers: list[dict[str, object]],
) -> None:
    plugin = MachineLearningStudioPlugin()
    message = "invalid tie breaker" if "unexpected" in tie_breakers[0] else "at most 8"
    with pytest.raises(ValueError, match=message):
        plugin.compare_trials(
            "ws",
            "lab",
            body={
                "spec": {"metric": "accuracy", "tie_breakers": tie_breakers},
                "trials": [{"parameters": {}, "metrics": {"accuracy": 1.0}}],
            },
        )
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


def test_search_route_derives_repeatable_per_trial_seeds_and_ids() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search-seed",
        "Search seed",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    observed_seeds: list[int] = []
    runner = plugin._runner
    original_run = runner.run

    def record_seed(candidate: Lab, rows: object, parameters: object) -> object:
        observed_seeds.append(candidate.seed)
        return original_run(candidate, rows, parameters)  # type: ignore[arg-type]

    runner.run = record_seed  # type: ignore[method-assign]
    body = {
        "spec": {
            "mode": "grid",
            "parameters": [{"name": "C", "values": [0.25, 1.0]}],
            "metric": "accuracy",
            "random_seed": 31,
        },
        "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
    }
    first = plugin.search_trials("ws", "search-seed", body=body)
    second = plugin.search_trials("ws", "search-seed", body=body)
    assert observed_seeds[:2] == observed_seeds[2:]
    assert len(set(observed_seeds[:2])) == 2
    assert {item["trial_id"] for item in first["items"]} == {
        item["trial_id"] for item in second["items"]
    }
    assert first["items"] == second["items"]
    plugin._coordinator.close()


def test_bayesian_search_stops_after_patience_without_improvement() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search-stop",
        "Search stop",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    calls: list[tuple[float, ...]] = []

    def run(_lab: Lab, _rows: object, parameters: object) -> object:
        calls.append(tuple(value for _, value in parameters))  # type: ignore[union-attr]
        return SimpleNamespace(model=SimpleNamespace(metrics={"accuracy": 0.5}))

    plugin._runner.run = run  # type: ignore[method-assign]
    result = plugin.search_trials(
        "ws",
        "search-stop",
        body={
            "spec": {
                "mode": "bayesian",
                "max_trials": 8,
                "parameters": [{"name": "C", "values": [0.1, 0.2, 0.3, 0.4, 0.5]}],
                "stop_policy": {"patience": 1, "min_improvement": 0.01},
            },
            "rows": [{"x": value, "target": value % 2} for value in range(1, 21)],
        },
    )
    assert len(calls) == 2
    assert len(result["items"]) == 2
    plugin._coordinator.close()


@pytest.mark.parametrize(
    ("name", "values", "message"),
    [
        ("C", [1.0, -1.0], "C search values"),
        ("max_iter", [100, 0], "max_iter search values"),
        ("seed", [3, -1], "seed search values"),
        ("unsupported", [1], "unsupported search parameter"),
    ],
)
def test_search_route_validates_entire_parameter_space_before_training(
    name: str, values: list[object], message: str
) -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search-preflight",
        "Search preflight",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)
    calls: list[Lab] = []

    def record_training(candidate: Lab, *_args: object, **_kwargs: object) -> object:
        calls.append(candidate)
        raise AssertionError("invalid search space must fail before training")

    plugin._runner.run = record_training  # type: ignore[method-assign]
    with pytest.raises(ValueError, match=message):
        plugin.search_trials(
            "ws",
            "search-preflight",
            body={
                "spec": {
                    "mode": "grid",
                    "parameters": [{"name": name, "values": values}],
                },
                "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
            },
        )
    assert calls == []
    plugin._coordinator.close()


def test_search_route_rejects_unknown_tie_breaker_fields_before_training() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._labs = LabService(InMemoryMLLabStore())
    lab = Lab(
        "search-tie-breaker-contract",
        "Search tie-breaker contract",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    plugin._labs.create(WorkspaceId("ws"), lab)

    def fail_training(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("invalid tie breaker must fail before training")

    plugin._runner.run = fail_training  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="invalid tie breaker"):
        plugin.search_trials(
            "ws",
            "search-tie-breaker-contract",
            body={
                "spec": {
                    "mode": "grid",
                    "tie_breakers": [
                        {"metric": "cost", "direction": "minimize", "unexpected": True}
                    ],
                },
                "rows": [{"x": n, "target": n % 2} for n in range(1, 21)],
            },
        )
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
