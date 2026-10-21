import json
from pathlib import Path

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import PIPELINE_SCHEMA_V2, FeatureSpec, Lab, PipelineIR, PipelineNode


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


def test_pipeline_v1_canonical_json_matches_documented_shape() -> None:
    pipeline = PipelineIR(
        (PipelineNode("profile", "profile"),), parameters=(("task", "classification"),)
    )

    payload = json.loads(pipeline.to_json())
    assert set(payload) == {"schema", "nodes", "parameters"}
    assert payload["schema"] == "ronin.ml-pipeline-ir/v1"
    assert payload["nodes"] == [{"depends_on": [], "id": "profile", "kind": "profile"}]
    assert payload["parameters"] == {"task": "classification"}
    assert PipelineIR.from_json(pipeline.to_json()) == pipeline


def test_pipeline_v2_serializes_explicit_data_only_node_configuration() -> None:
    pipeline = PipelineIR(
        (PipelineNode("candidate", "train", config={"algorithm": "linear_regression"}),),
        schema=PIPELINE_SCHEMA_V2,
    )
    payload = json.loads(pipeline.to_json())
    assert payload["schema"] == "ronin.ml-pipeline-ir/v2"
    assert payload["nodes"][0]["config"] == {"algorithm": "linear_regression"}
    assert PipelineIR.from_json(pipeline.to_json()) == pipeline


def test_pipeline_v1_rejects_configured_nodes() -> None:
    with pytest.raises(ValueError, match="v1 nodes cannot contain configuration"):
        PipelineIR((PipelineNode("train", "train", config={"algorithm": "unsafe"}),))


def test_pipeline_config_rejects_non_string_object_keys() -> None:
    with pytest.raises(ValueError, match="object keys must be strings"):
        PipelineNode("train", "train", config={1: "invalid"})


def test_pipeline_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="acyclic"):
        PipelineIR((PipelineNode("a", "prepare", ("b",)), PipelineNode("b", "train", ("a",))))


def test_pipeline_execution_order_is_stable_and_dependency_respecting() -> None:
    pipeline = PipelineIR(
        (
            PipelineNode("finish", "select", ("left", "right")),
            PipelineNode("right", "evaluate", ("start",)),
            PipelineNode("left", "prepare", ("start",)),
            PipelineNode("start", "profile"),
        )
    )

    assert [node.id for node in pipeline.execution_order()] == [
        "start",
        "left",
        "right",
        "finish",
    ]


def test_pipeline_node_count_is_bounded() -> None:
    nodes = tuple(
        PipelineNode(f"stage-{index}", "profile", (f"stage-{index - 1}",) if index else ())
        for index in range(21)
    )
    with pytest.raises(ValueError, match="cannot contain more than 20 nodes"):
        PipelineIR(nodes)


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
