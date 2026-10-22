import json
from pathlib import Path

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import (
    PIPELINE_SCHEMA_V2,
    PIPELINE_SCHEMA_V3,
    FeatureSpec,
    Lab,
    PipelineIR,
    PipelineNode,
)
from studio_ml.orchestration import _retry_invalidated_node_ids


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
        for index in range(25)
    )
    with pytest.raises(ValueError, match="cannot contain more than 24 nodes"):
        PipelineIR(nodes)


def _v3_pipeline_nodes() -> tuple[PipelineNode, ...]:
    return (
        PipelineNode("profile", "profile"),
        PipelineNode("quality", "quality_gate", inputs=(("profile", ("profile.out",)),)),
        PipelineNode(
            "prepare_a",
            "prepare",
            config={"preprocessor": "identity"},
            inputs=(("quality", ("quality.out",)),),
        ),
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
        PipelineNode("evaluate_a", "evaluate", inputs=(("model", ("train_a.out",)),)),
        PipelineNode("evaluate_b", "evaluate", inputs=(("model", ("train_b.out",)),)),
        PipelineNode(
            "select", "select", inputs=(("candidates", ("evaluate_b.out", "evaluate_a.out")),)
        ),
    )


def test_pipeline_v3_uses_versioned_typed_inputs_and_stable_topological_order() -> None:
    pipeline = PipelineIR(_v3_pipeline_nodes(), schema=PIPELINE_SCHEMA_V3)
    payload = json.loads(pipeline.to_json())
    assert payload["schema"] == PIPELINE_SCHEMA_V3
    assert payload["nodes"][0]["stage_version"] == 1
    assert "depends_on" not in payload["nodes"][1]
    assert payload["nodes"][1]["inputs"] == {"profile": ["profile.out"]}
    assert PipelineIR.from_json(pipeline.to_json()) == pipeline
    permuted = PipelineIR(tuple(reversed(_v3_pipeline_nodes())), schema=PIPELINE_SCHEMA_V3)
    assert permuted.digest == pipeline.digest
    assert [node.id for node in pipeline.execution_order()] == [
        "profile",
        "quality",
        "prepare_a",
        "prepare_b",
        "train_a",
        "train_b",
        "evaluate_a",
        "evaluate_b",
        "select",
    ]


def test_retrying_pipeline_v3_stage_invalidates_all_matching_branches() -> None:
    pipeline = PipelineIR(_v3_pipeline_nodes(), schema=PIPELINE_SCHEMA_V3)

    assert _retry_invalidated_node_ids(pipeline, "prepare") == {
        "prepare_a",
        "prepare_b",
        "train_a",
        "train_b",
        "evaluate_a",
        "evaluate_b",
        "select",
    }
    assert _retry_invalidated_node_ids(pipeline, "node:prepare_a") == {
        "prepare_a",
        "train_a",
        "evaluate_a",
        "select",
    }


def test_retry_selector_disambiguates_node_ids_that_match_stage_kinds() -> None:
    nodes = tuple(
        PipelineNode(
            "train" if node.id == "profile" else node.id,
            node.kind,
            config=node.config,
            inputs=tuple(
                (
                    port,
                    tuple(
                        "train.out" if reference == "profile.out" else reference
                        for reference in references
                    ),
                )
                for port, references in node.inputs
            ),
            stage_version=node.stage_version,
        )
        for node in _v3_pipeline_nodes()
    )
    pipeline = PipelineIR(nodes, schema=PIPELINE_SCHEMA_V3)

    assert _retry_invalidated_node_ids(pipeline, "train") == {
        "train_a",
        "train_b",
        "evaluate_a",
        "evaluate_b",
        "select",
    }
    assert _retry_invalidated_node_ids(pipeline, "node:train") == {
        "train",
        "quality",
        "prepare_a",
        "prepare_b",
        "train_a",
        "train_b",
        "evaluate_a",
        "evaluate_b",
        "select",
    }


def test_pipeline_v3_rejects_bad_stage_versions_ports_types_and_orphans() -> None:
    nodes = list(_v3_pipeline_nodes())
    nodes[4] = PipelineNode(
        "train_a",
        "train",
        config={"algorithm": "logistic_regression"},
        stage_version=2,
        inputs=(("prepared", ("prepare_a.out",)),),
    )
    with pytest.raises(ValueError, match="stage or version"):
        PipelineIR(tuple(nodes), schema=PIPELINE_SCHEMA_V3)

    nodes = list(_v3_pipeline_nodes())
    nodes[1] = PipelineNode("quality", "quality_gate", inputs=(("profile", ("prepare_a.out",)),))
    with pytest.raises(ValueError, match="incompatible output type"):
        PipelineIR(tuple(nodes), schema=PIPELINE_SCHEMA_V3)

    nodes = (*_v3_pipeline_nodes(), PipelineNode("unused", "profile"))
    with pytest.raises(ValueError, match="one profile"):
        PipelineIR(nodes, schema=PIPELINE_SCHEMA_V3)


def test_pipeline_v3_rejects_config_and_graph_byte_limits() -> None:
    from studio_ml.domain import MAX_PIPELINE_BYTES_V3

    nodes = list(_v3_pipeline_nodes())
    nodes[2] = PipelineNode(
        "prepare_a",
        "prepare",
        config={"preprocessor": "identity", "excess": "x"},
        inputs=(("quality", ("quality.out",)),),
    )
    with pytest.raises(ValueError, match="unsupported fields"):
        PipelineIR(tuple(nodes), schema=PIPELINE_SCHEMA_V3)
    with pytest.raises(ValueError, match="payload exceeds the byte limit"):
        PipelineIR(
            _v3_pipeline_nodes(),
            parameters=(("padding", "x" * MAX_PIPELINE_BYTES_V3),),
            schema=PIPELINE_SCHEMA_V3,
        )
    with pytest.raises(ValueError, match="at most six"):
        PipelineIR(
            _v3_pipeline_nodes(),
            parameters=tuple((str(index), str(index)) for index in range(7)),
            schema=PIPELINE_SCHEMA_V3,
        )


def test_pipeline_v3_builtin_registry_is_immutable() -> None:
    from studio_ml.pipeline_stages import BUILTIN_STAGE_REGISTRY

    with pytest.raises(TypeError):
        BUILTIN_STAGE_REGISTRY["unsafe"] = BUILTIN_STAGE_REGISTRY["profile"]  # type: ignore[index]


def test_pipeline_v3_rejects_unknown_references_and_excessive_fanout() -> None:
    nodes = list(_v3_pipeline_nodes())
    nodes[1] = PipelineNode("quality", "quality_gate", inputs=(("profile", ("missing.out",)),))
    with pytest.raises(ValueError, match="unknown node"):
        PipelineIR(tuple(nodes), schema=PIPELINE_SCHEMA_V3)

    branch_nodes = [
        PipelineNode("profile", "profile"),
        PipelineNode("quality", "quality_gate", inputs=(("profile", ("profile.out",)),)),
        PipelineNode("prepare", "prepare", inputs=(("quality", ("quality.out",)),)),
    ]
    evaluations = []
    for index in range(9):
        branch_nodes.append(
            PipelineNode(
                f"train-{index}",
                "train",
                config={"algorithm": "logistic_regression"},
                inputs=(("prepared", ("prepare.out",)),),
            )
        )
        branch_nodes.append(
            PipelineNode(
                f"evaluate-{index}",
                "evaluate",
                inputs=(("model", (f"train-{index}.out",)),),
            )
        )
        evaluations.append(f"evaluate-{index}.out")
    branch_nodes.append(
        PipelineNode("select", "select", inputs=(("candidates", tuple(evaluations)),))
    )
    with pytest.raises(ValueError, match="fan-out exceeds 8"):
        PipelineIR(tuple(branch_nodes), schema=PIPELINE_SCHEMA_V3)


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
