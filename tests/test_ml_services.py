"""Application-service contract tests."""
# ruff: noqa: E501

import pytest
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.services import InMemoryMLLabStore, LabService, MLLabConflict


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
