"""Application-service contract tests."""
# ruff: noqa: E501

from types import SimpleNamespace

import pytest

from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.service import compare_model_evaluations
from studio_ml.services import InMemoryMLLabStore, LabService, MLLabConflict


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
