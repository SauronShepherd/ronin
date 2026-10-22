"""Application-service contract tests."""
# ruff: noqa: E501

from types import SimpleNamespace

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import PIPELINE_SCHEMA_V2, FeatureSpec, Lab
from studio_ml.service import compare_model_evaluations
from studio_ml.services import (
    InMemoryMLLabStore,
    LabService,
    MLLabConflict,
    compile_lab_pipeline,
)


def test_model_evaluations_rank_deterministically_and_skip_missing_metrics() -> None:
    low = SimpleNamespace(
        model_id=SimpleNamespace(value="model"),
        version=SimpleNamespace(value="1"),
        execution_ref="run-low",
        metrics=(SimpleNamespace(name="accuracy", value=0.8),),
    )
    high = SimpleNamespace(
        model_id=SimpleNamespace(value="model"),
        version=SimpleNamespace(value="2"),
        execution_ref="run-high",
        metrics=(SimpleNamespace(name="accuracy", value=0.9),),
    )
    missing = SimpleNamespace(
        model_id=SimpleNamespace(value="other"),
        version=SimpleNamespace(value="1"),
        execution_ref="run-missing",
        metrics=(SimpleNamespace(name="loss", value=0.1),),
    )
    assert compare_model_evaluations((low, missing, high), metric="accuracy") == (high, low)


def test_lab_service_is_idempotent_for_same_identity() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "churn",
        "classification",
        (FeatureSpec("age"),),
    )
    service = LabService(InMemoryMLLabStore())
    assert service.create(WorkspaceId("ws"), lab) == lab
    with pytest.raises(MLLabConflict):
        service.create(WorkspaceId("ws"), lab)


def test_compile_produces_valid_pipeline() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "churn",
        "classification",
        (FeatureSpec("age"),),
    )
    service = LabService(InMemoryMLLabStore())
    service.create(WorkspaceId("ws"), lab)
    pipeline = service.compile(WorkspaceId("ws"), "churn")
    assert [node.kind for node in pipeline.nodes] == [
        "profile",
        "quality_gate",
        "prepare",
        "train",
        "evaluate",
        "select",
    ]


def test_compile_candidate_algorithms_produces_pinned_v2_pipeline() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "churn",
        "classification",
        (FeatureSpec("age"),),
    )
    service = LabService(InMemoryMLLabStore())
    service.create(WorkspaceId("ws"), lab)
    pipeline = service.compile(
        WorkspaceId("ws"),
        "churn",
        candidate_algorithms=("logistic_regression", "decision_tree_classifier"),
    )

    assert pipeline.schema == PIPELINE_SCHEMA_V2
    assert [node.config.get("algorithm") for node in pipeline.nodes if node.kind == "train"] == [
        "logistic_regression",
        "decision_tree_classifier",
    ]
    assert pipeline.nodes[-1].config == {"metric": "accuracy", "direction": "maximize"}


def test_compile_candidate_algorithms_defaults_error_metric_to_minimize() -> None:
    lab = Lab(
        "prices",
        "Prices",
        "finance",
        AssetRef(AssetId("prices"), AssetVersion("v1")),
        "price",
        "regression",
        (FeatureSpec("day"),),
    )
    pipeline = compile_lab_pipeline(
        lab,
        candidate_algorithms=("linear_regression", "decision_tree_regressor"),
        selection_metric="mean_squared_error",
    )
    assert pipeline.nodes[-1].config["direction"] == "minimize"


def test_compile_candidate_preprocessors_branches_and_pins_each_prepare() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "churn",
        "classification",
        (FeatureSpec("age", "numeric"), FeatureSpec("region", "categorical")),
    )
    pipeline = compile_lab_pipeline(
        lab,
        algorithm="decision_tree_classifier",
        candidate_preprocessors=("one_hot", "one_hot_median_impute"),
    )

    prepares = [node for node in pipeline.nodes if node.kind == "prepare"]
    trains = [node for node in pipeline.nodes if node.kind == "train"]
    assert pipeline.schema == PIPELINE_SCHEMA_V2
    assert [node.config["preprocessor"] for node in prepares] == [
        "one_hot",
        "one_hot_median_impute",
    ]
    assert [node.depends_on for node in trains] == [(node.id,) for node in prepares]
    assert all(node.config["algorithm"] == "decision_tree_classifier" for node in trains)
    assert len(pipeline.nodes) == 9


def test_compile_candidate_preprocessors_rejects_invalid_or_incompatible_lists() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "churn",
        "classification",
        (FeatureSpec("age", "numeric"),),
    )
    for preprocessors in (("identity",), ("identity", "identity"), ("unknown", "identity")):
        with pytest.raises(ValueError, match="candidate_preprocessors|preprocessor"):
            compile_lab_pipeline(lab, candidate_preprocessors=preprocessors)
    with pytest.raises(ValueError, match="one_hot preprocessing"):
        compile_lab_pipeline(lab, candidate_preprocessors=("identity", "one_hot"))
    with pytest.raises(ValueError, match="candidate selection options"):
        compile_lab_pipeline(
            lab,
            candidate_algorithms=("logistic_regression", "decision_tree_classifier"),
            candidate_preprocessors=("identity", "standard_scale"),
        )


def test_compile_clustering_candidates_pins_counts_and_inertia_policy() -> None:
    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        None,
        "clustering",
        (FeatureSpec("x", "numeric"),),
    )
    pipeline = compile_lab_pipeline(lab, candidate_cluster_counts=(2, 4, 3))
    assert pipeline.schema == PIPELINE_SCHEMA_V2
    assert [node.config["clusters"] for node in pipeline.nodes if node.kind == "train"] == [
        2,
        4,
        3,
    ]
    select = next(node for node in pipeline.nodes if node.kind == "select")
    assert select.config == {"direction": "maximize", "metric": "calinski_harabasz"}


@pytest.mark.parametrize("counts", [(2, 2), (1, 3), (2, 33), (True, 3)])
def test_compile_clustering_candidates_rejects_invalid_counts(counts: tuple[int, ...]) -> None:
    lab = Lab(
        "segments",
        "Segments",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        None,
        "clustering",
        (FeatureSpec("x", "numeric"),),
    )
    with pytest.raises(ValueError, match="candidate_cluster_counts"):
        compile_lab_pipeline(lab, candidate_cluster_counts=counts)
