"""Local runner contract tests."""
# ruff: noqa: E501

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import PIPELINE_SCHEMA_V2, FeatureSpec, Lab, PipelineIR, PipelineNode
from studio_ml.runner import LocalExperimentRunner, _checkpoint_runtime_fingerprint
from studio_ml.runtime import train_tabular
from studio_ml.services import compile_lab_pipeline


def _lab() -> Lab:
    return Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x", "numeric"),),
    )


def _rows() -> list[dict[str, object]]:
    return [{"x": value, "target": value % 2} for value in range(1, 21)]


def _cluster_lab() -> Lab:
    return Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        None,
        "clustering",
        (FeatureSpec("x", "numeric"),),
    )


class _CheckpointBackend:
    backend_id = "local.sklearn"
    display_name = "test backend"
    capabilities = None

    def __init__(self, *, fail_on_train: bool = False) -> None:
        self.fail_on_train = fail_on_train
        self.train_calls = 0

    def train(self, request, rows):
        self.train_calls += 1
        if self.fail_on_train:
            raise AssertionError("checkpointed train node must not execute")
        return train_tabular(rows, request.spec)


def test_local_runner_returns_portable_result_deterministically() -> None:
    runner = LocalExperimentRunner()
    first = runner.run(_lab(), _rows())
    second = runner.run(_lab(), _rows())
    assert first.to_payload() == second.to_payload()
    assert first.artifact_digest.startswith("sha256:")
    assert first.row_count == 20


def test_local_runner_applies_effective_hyperparameters() -> None:
    runner = LocalExperimentRunner()
    default = runner.run(_lab(), _rows())
    tuned = runner.run(_lab(), _rows(), (("C", 0.1), ("max_iter", 200)))
    assert default.artifact_digest != tuned.artifact_digest
    assert b"hyperparameters" in tuned.model.artifact_bytes


def test_local_runner_executes_pinned_pipeline_and_rejects_unsupported_graph() -> None:
    lab = _lab()
    runner = LocalExperimentRunner()
    compiled = compile_lab_pipeline(lab)
    reordered = PipelineIR(tuple(reversed(compiled.nodes)), compiled.parameters)

    assert (
        runner.execute_pipeline(lab, _rows(), compiled).to_payload()
        == runner.execute_pipeline(lab, _rows(), reordered).to_payload()
    )

    unsupported = PipelineIR(
        tuple(
            PipelineNode(node.id, "register", node.depends_on)
            if node.kind == "quality_gate"
            else node
            for node in compiled.nodes
        ),
        compiled.parameters,
    )
    with pytest.raises(ValueError, match="exactly one supported node"):
        runner.execute_pipeline(lab, _rows(), unsupported)


def test_pipeline_selected_algorithm_is_executed_and_bound_to_checkpoints() -> None:
    lab = _lab()
    default_pipeline = compile_lab_pipeline(lab)
    selected_pipeline = compile_lab_pipeline(lab, algorithm="decision_tree_classifier")
    assert selected_pipeline.digest != default_pipeline.digest

    checkpoints: dict[str, dict[str, object]] = {}
    first_backend = _CheckpointBackend()
    default_result = LocalExperimentRunner((first_backend,)).execute_pipeline(
        lab,
        _rows(),
        default_pipeline,
        checkpoint_save=lambda node_id, payload: checkpoints.__setitem__(node_id, payload),
    )
    assert default_result.to_payload()["algorithm"] == "logistic_regression"

    selected_backend = _CheckpointBackend()
    selected_result = LocalExperimentRunner((selected_backend,)).execute_pipeline(
        lab,
        _rows(),
        selected_pipeline,
        checkpoint_load=checkpoints.get,
    )

    assert selected_result.to_payload()["algorithm"] == "decision_tree_classifier"
    assert selected_backend.train_calls == 1


def test_v2_pipeline_trains_multiple_candidates_and_selects_deterministically() -> None:
    lab = _lab()
    pipeline = PipelineIR(
        (
            PipelineNode("profile", "profile"),
            PipelineNode("quality", "quality_gate", ("profile",)),
            PipelineNode("prepare", "prepare", ("quality",)),
            PipelineNode("tree", "train", ("prepare",), {"algorithm": "decision_tree_classifier"}),
            PipelineNode("linear", "train", ("prepare",), {"algorithm": "logistic_regression"}),
            PipelineNode("tree_eval", "evaluate", ("tree",)),
            PipelineNode("linear_eval", "evaluate", ("linear",)),
            PipelineNode(
                "select",
                "select",
                ("tree_eval", "linear_eval"),
                {"metric": "accuracy", "direction": "maximize"},
            ),
        ),
        parameters=(("lab_digest", lab.digest), ("task", lab.task)),
        schema=PIPELINE_SCHEMA_V2,
    )
    first = LocalExperimentRunner().execute_pipeline(lab, _rows(), pipeline)
    second = LocalExperimentRunner().execute_pipeline(lab, _rows(), pipeline)

    assert first.to_payload() == second.to_payload()
    assert first.model.algorithm in {"decision_tree_classifier", "logistic_regression"}


def test_v2_clustering_pipeline_selects_highest_calinski_harabasz_candidate() -> None:
    from studio_ml.clustering import calinski_harabasz, fit_kmeans, inertia

    lab = _cluster_lab()
    rows = [{"x": value} for value in range(1, 21)]
    pipeline = compile_lab_pipeline(lab, candidate_cluster_counts=(2, 4, 3))
    first = LocalExperimentRunner().execute_pipeline(lab, rows, pipeline)
    second = LocalExperimentRunner().execute_pipeline(lab, rows, pipeline)
    assert first.to_payload() == second.to_payload()
    expected = {
        count: calinski_harabasz(fit_kmeans(rows, ("x",), count), rows, ("x",))
        for count in (2, 3, 4)
    }
    assert len(first.model.centroids) == max(expected, key=expected.get)
    assert first.selection_metric == "calinski_harabasz"
    assert first.selection_score == max(expected.values())
    assert first.inertia == inertia(first.model, rows, ("x",))


def test_v2_clustering_pipeline_rejects_candidate_count_before_any_training() -> None:
    lab = _cluster_lab()
    pipeline = compile_lab_pipeline(lab, candidate_cluster_counts=(2, 21))
    with pytest.raises(ValueError, match="less than row count"):
        LocalExperimentRunner().execute_pipeline(
            lab, [{"x": value} for value in range(1, 21)], pipeline
        )


def test_v2_pipeline_rejects_unsupported_graph_before_training() -> None:
    lab = _lab()
    backend = _CheckpointBackend()
    pipeline = PipelineIR(
        (
            PipelineNode("profile", "profile"),
            PipelineNode("quality", "quality_gate", ("profile",)),
            PipelineNode("prepare", "prepare", ("quality",)),
            PipelineNode(
                "candidate", "train", ("quality",), {"algorithm": "decision_tree_classifier"}
            ),
            PipelineNode(
                "candidate_b", "train", ("prepare",), {"algorithm": "logistic_regression"}
            ),
            PipelineNode("evaluate", "evaluate", ("candidate",)),
            PipelineNode("evaluate_b", "evaluate", ("candidate_b",)),
            PipelineNode("select", "select", ("evaluate", "evaluate_b")),
        ),
        parameters=(("lab_digest", lab.digest),),
        schema=PIPELINE_SCHEMA_V2,
    )
    with pytest.raises(ValueError, match="train nodes must depend on prepare"):
        LocalExperimentRunner((backend,)).execute_pipeline(lab, _rows(), pipeline)
    assert backend.train_calls == 0


def test_pipeline_preprocessor_is_pinned_and_executed() -> None:
    import json

    lab = _lab()
    pipeline = compile_lab_pipeline(lab, preprocessor="standard_scale")
    result = LocalExperimentRunner().execute_pipeline(lab, _rows(), pipeline)
    artifact = json.loads(result.model.artifact_bytes)
    assert artifact["preprocessing"]["kind"] == "standard_scale"


def test_numeric_lab_can_pin_median_imputation() -> None:
    import json

    lab = _lab()
    pipeline = compile_lab_pipeline(lab, preprocessor="median_impute")
    rows = _rows()
    rows[0]["x"] = None
    result = LocalExperimentRunner().execute_pipeline(lab, rows, pipeline)
    artifact = json.loads(result.model.artifact_bytes)
    assert artifact["preprocessing"]["kind"] == "median_impute"
    assert len(artifact["preprocessing"]["medians"]) == len(lab.features)


def test_one_hot_pipeline_uses_lab_categorical_roles() -> None:
    import json

    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("segment", "categorical"), FeatureSpec("age", "numeric")),
    )
    rows = [
        {"segment": "blue" if index % 2 else "red", "age": float(index), "target": index % 2}
        for index in range(20)
    ]
    pipeline = compile_lab_pipeline(lab, preprocessor="one_hot")
    result = LocalExperimentRunner().execute_pipeline(lab, rows, pipeline)
    artifact = json.loads(result.model.artifact_bytes)
    assert artifact["preprocessing"]["categories"]["segment"] == ["blue", "red"]


def test_pipeline_composes_one_hot_and_numeric_median_imputation() -> None:
    import json

    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("segment", "categorical"), FeatureSpec("age", "numeric")),
    )
    rows = [
        {
            "segment": "blue" if index % 2 else "red",
            "age": None if index == 0 else float(index),
            "target": index % 2,
        }
        for index in range(20)
    ]
    pipeline = compile_lab_pipeline(lab, preprocessor="one_hot_median_impute")
    result = LocalExperimentRunner().execute_pipeline(lab, rows, pipeline)
    preprocessing = json.loads(result.model.artifact_bytes)["preprocessing"]
    assert preprocessing["kind"] == "one_hot_median_impute"
    assert preprocessing["categories"]["segment"] == ["blue", "red"]
    assert "age" in preprocessing["medians"]


def test_local_runner_restores_all_persisted_node_outputs_without_reexecution() -> None:
    lab = _lab()
    pipeline = compile_lab_pipeline(lab)
    checkpoints: dict[str, dict[str, object]] = {}
    backend = _CheckpointBackend()
    first = LocalExperimentRunner((backend,)).execute_pipeline(
        lab,
        _rows(),
        pipeline,
        checkpoint_save=lambda node_id, payload: checkpoints.__setitem__(node_id, payload),
    )
    assert len(checkpoints) == 6
    assert len(first.runtime_fingerprint) == 64
    assert (
        checkpoints["select"]["checkpoint"]["value"]["runtime_fingerprint"]
        == first.runtime_fingerprint
    )
    assert backend.train_calls == 1

    resumed_backend = _CheckpointBackend(fail_on_train=True)
    resumed = LocalExperimentRunner((resumed_backend,)).execute_pipeline(
        lab,
        _rows(),
        pipeline,
        checkpoint_load=checkpoints.get,
    )
    assert resumed.to_payload() == first.to_payload()
    assert resumed_backend.train_calls == 0


def test_local_runner_discards_checkpoints_from_another_runtime() -> None:
    lab = _lab()
    pipeline = compile_lab_pipeline(lab)
    checkpoints: dict[str, dict[str, object]] = {}
    first = LocalExperimentRunner((_CheckpointBackend(),)).execute_pipeline(
        lab,
        _rows(),
        pipeline,
        checkpoint_save=lambda node_id, payload: checkpoints.__setitem__(node_id, payload),
    )
    stale = {
        node_id: {**payload, "runtime_fingerprint": "0" * 64}
        for node_id, payload in checkpoints.items()
    }

    replacement = _CheckpointBackend()
    resumed = LocalExperimentRunner((replacement,)).execute_pipeline(
        lab,
        _rows(),
        pipeline,
        checkpoint_load=stale.get,
    )

    assert replacement.train_calls == 1
    assert resumed.to_payload() == first.to_payload()


def test_checkpoint_runtime_fingerprint_includes_execution_options() -> None:
    backend = _CheckpointBackend()
    base = _checkpoint_runtime_fingerprint(backend, parameters=(), clusters=2, max_iterations=100)
    changed = _checkpoint_runtime_fingerprint(
        backend, parameters=(("C", 0.5),), clusters=3, max_iterations=100
    )
    assert base is not None
    assert changed is not None
    assert base != changed


def test_pipeline_recomputes_downstream_checkpoints_after_dependency_changes() -> None:
    lab = _lab()
    pipeline = compile_lab_pipeline(lab)
    checkpoints: dict[str, dict[str, object]] = {}
    first = LocalExperimentRunner((_CheckpointBackend(),)).execute_pipeline(
        lab,
        _rows(),
        pipeline,
        checkpoint_save=lambda node_id, payload: checkpoints.__setitem__(node_id, payload),
    )
    train_node_id = next(node.id for node in pipeline.nodes if node.kind == "train")
    train_checkpoint = checkpoints[train_node_id]
    checkpoint_payload = train_checkpoint["checkpoint"]
    train_value = dict(checkpoint_payload["value"])
    metrics = [list(metric) for metric in train_value["metrics"]]
    metrics[0][1] = float(metrics[0][1]) + 0.125
    train_value["metrics"] = metrics
    checkpoints[train_node_id] = {
        **train_checkpoint,
        "checkpoint": {**checkpoint_payload, "value": train_value},
    }

    resumed_backend = _CheckpointBackend(fail_on_train=True)
    resumed = LocalExperimentRunner((resumed_backend,)).execute_pipeline(
        lab,
        _rows(),
        pipeline,
        checkpoint_load=checkpoints.get,
    )

    assert resumed_backend.train_calls == 0
    assert resumed.to_payload()["metrics"] != first.to_payload()["metrics"]
