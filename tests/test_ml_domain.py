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


def test_lab_rejects_boolean_seed_and_non_finite_test_fraction() -> None:
    arguments = {
        "id": "churn",
        "name": "Churn",
        "project_id": "crm",
        "dataset": _dataset(),
        "target": "churn",
        "task": "classification",
        "features": (FeatureSpec("age", "numeric"),),
    }
    with pytest.raises(ValueError, match="seed"):
        Lab(**arguments, seed=True)
    with pytest.raises(ValueError, match="test fraction"):
        Lab(**arguments, test_fraction=float("nan"))
