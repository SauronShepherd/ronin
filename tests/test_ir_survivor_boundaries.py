from __future__ import annotations

import pytest
import studio_core.ir as ir
from studio_core import (
    Edge,
    FrozenList,
    FrozenMap,
    Node,
    NodeId,
    OperatorRef,
    Origin,
    Pipeline,
    Port,
    SchemaRef,
    freeze_value,
    thaw_value,
)


def _node(instance_key: str = "node") -> Node:
    return Node.create(
        operator=OperatorRef("transform.identity", 2),
        instance_key=instance_key,
        params={"b": [2, 1], "a": {"enabled": True}},
        inputs=(Port("in", "batch", SchemaRef("input", "v1")),),
        outputs=(Port("out", "batch", SchemaRef("output", "v1")),),
        origin=Origin("imported", "source.py:1"),
        ownership="RECONCILED",
        label="display-only",
    )


@pytest.mark.parametrize("value", [None, False, True, 0, -1, 1.5, "text"])
def test_freeze_and_thaw_preserve_each_scalar_type(value: object) -> None:
    frozen = freeze_value(value)
    assert thaw_value(frozen) == value
    assert type(thaw_value(frozen)) is type(value)


def test_freeze_value_sorts_mapping_keys_but_preserves_sequence_order() -> None:
    frozen = freeze_value({"z": [2, 1], "a": {"y": 2, "x": 1}})
    assert frozen == FrozenMap(
        (
            ("a", FrozenMap((("x", 1), ("y", 2)))),
            ("z", FrozenList((2, 1))),
        )
    )
    assert thaw_value(frozen) == {"a": {"x": 1, "y": 2}, "z": [2, 1]}


def test_frozen_comparison_key_distinguishes_equal_python_values_by_type() -> None:
    keys = {
        ir._frozen_comparison_key(freeze_value(value))
        for value in (None, False, 0, 0.0, "0", [0], {"value": 0})
    }
    assert len(keys) == 7


def test_node_constructor_canonicalizes_params_and_rejects_duplicate_names() -> None:
    canonical = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="node",
        params={"a": 2, "z": 1},
    )
    node = Node(
        canonical.id,
        "node",
        OperatorRef("transform.identity"),
        params=(("z", 1), ("a", 2)),
        inputs=(),
        outputs=(),
    )
    assert node.params == (("a", 2), ("z", 1))

    with pytest.raises(ValueError, match="parameter names must be unique"):
        Node(
            NodeId("invalid"),
            "duplicate",
            OperatorRef("transform.identity"),
            params=(("a", 1), ("a", 2)),
        )


def test_node_param_uses_sorted_lookup_and_returns_none_for_missing_values() -> None:
    node = _node()
    assert node.param("a") == FrozenMap((("enabled", True),))
    assert node.param("b") == FrozenList((2, 1))
    assert node.param("missing") is None


def test_pipeline_serialization_preserves_empty_and_optional_metadata() -> None:
    node = Node.create(
        operator=OperatorRef("source.empty"),
        instance_key="empty",
        origin=Origin("system"),
        ownership="GRAPH",
        label=None,
    )
    pipeline = Pipeline((node,))
    assert Pipeline.from_data(pipeline.to_data()) == pipeline
    assert pipeline.to_data()["nodes"][0]["origin"] == {"view": "system", "reference": None}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source", None, "edge.source must be a string"),
        ("source_port", None, "edge.source_port must be a string"),
        ("target", None, "edge.target must be a string"),
        ("target_port", None, "edge.target_port must be a string"),
    ],
)
def test_edge_parser_reports_each_required_field_type(
    field: str, value: object, message: str
) -> None:
    data = {
        "source": "source",
        "source_port": "out",
        "target": "target",
        "target_port": "in",
    }
    data[field] = value
    with pytest.raises(TypeError, match=f"^{message}$"):
        ir._edge_from_data(data)


def test_pipeline_rejects_missing_top_level_collections_before_graph_validation() -> None:
    with pytest.raises(TypeError, match="config"):
        Pipeline.from_data({"nodes": [], "edges": []})
    with pytest.raises(TypeError, match="nodes"):
        Pipeline.from_data({"config": {"name": "main"}, "edges": []})
    with pytest.raises(TypeError, match="edges"):
        Pipeline.from_data({"config": {"name": "main"}, "nodes": []})


def test_pipeline_rejects_duplicate_edges_by_value_even_when_nodes_are_distinct() -> None:
    source = Node.create(
        operator=OperatorRef("source"), instance_key="source", outputs=(Port("out"),)
    )
    target = Node.create(operator=OperatorRef("sink"), instance_key="target", inputs=(Port("in"),))
    edge = Edge(source.id, "out", target.id, "in")
    with pytest.raises(ValueError, match="^duplicate edge$"):
        Pipeline((source, target), (edge, Edge(source.id, "out", target.id, "in")))
