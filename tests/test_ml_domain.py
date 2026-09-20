import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab, PipelineIR, PipelineNode


def _dataset() -> AssetRef:
    return AssetRef(AssetId("customers"), AssetVersion("sha256:test"))


def test_lab_round_trips_canonical_json() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        _dataset(),
        "churn",
        "classification",
        (FeatureSpec("age", "numeric"),),
    )
    assert Lab.from_json(lab.to_json()) == lab


def test_pipeline_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="acyclic"):
        PipelineIR((PipelineNode("a", "prepare", ("b",)), PipelineNode("b", "train", ("a",))))
