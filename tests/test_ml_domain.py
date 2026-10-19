import json
from pathlib import Path

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


def test_lab_v1_golden_clustering_payload_preserves_unknown_fields() -> None:
    fixture = Path(__file__).parent / "fixtures/contracts/ml-lab-v1-clustering.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))

    lab = Lab.from_payload(expected)

    assert lab.task == "clustering"
    assert lab.target is None
    assert lab.test_fraction == 0.75
    assert lab.to_payload() == expected
    assert Lab.from_json(lab.to_json()) == lab
    assert Lab.from_json(lab.to_json()).digest == lab.digest


def test_lab_metadata_is_json_valued_and_immutable() -> None:
    lab = Lab(
        "lab",
        "Lab",
        "project",
        _dataset(),
        "target",
        "regression",
        (FeatureSpec("x"),),
        metadata={"ui": {"collapsed": [True, None]}},
    )
    with pytest.raises(TypeError):
        lab.metadata["other"] = "value"
    with pytest.raises(TypeError, match="canonical JSON"):
        Lab(
            "bad-lab",
            "Bad Lab",
            "project",
            _dataset(),
            "target",
            "regression",
            (FeatureSpec("x"),),
            metadata={"ui": object()},
        )
