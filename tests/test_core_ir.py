from dataclasses import FrozenInstanceError

from hypothesis import given
from hypothesis import strategies as st
import pytest
from studio_core import (
    Edge,
    FrozenList,
    FrozenMap,
    Node,
    NodeId,
    OperatorRef,
    Origin,
    Pipeline,
    PipelineConfig,
    Port,
    SchemaRef,
    freeze_value,
    thaw_value,
)

BATCH_IN = Port("in", "batch")
BATCH_OUT = Port("out", "batch")
STREAM_OUT = Port("out", "stream")


def _node(key: str, *, inputs: tuple[Port, ...] = (), outputs: tuple[Port, ...] = ()) -> Node:
    return Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key=key,
        params={"nested": {"b": [2, 1], "a": True}},
        inputs=inputs,
        outputs=outputs,
        origin=Origin("graph", "canvas"),
        label=f"label-{key}",
    )


def test_ir_objects_are_immutable() -> None:
    node_id = NodeId("a")
    with pytest.raises(FrozenInstanceError):
        node_id.value = "b"  # type: ignore[misc]


def test_operator_version_must_be_positive() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        OperatorRef("invalid", 0)


def test_freeze_value_is_canonical_hashable_and_round_trips() -> None:
    first = freeze_value({"b": [2, 1], "a": {"enabled": True}})
    second = freeze_value({"a": {"enabled": True}, "b": [2, 1]})
    assert first == second
    assert isinstance(first, FrozenMap)
    assert isinstance(dict(first.items)["b"], FrozenList)
    assert thaw_value(first) == {"a": {"enabled": True}, "b": [2, 1]}
    assert hash(first) == hash(second)


def test_freeze_value_rejects_non_string_mapping_keys_and_unsupported_values() -> None:
    with pytest.raises(TypeError, match="keys"):
        freeze_value({1: "invalid"})
    with pytest.raises(TypeError, match="unsupported"):
        freeze_value(object())


def test_node_identity_ignores_label_but_uses_stable_instance_key() -> None:
    first = Node.create(
        operator=OperatorRef("source.table"),
        instance_key="source-slot",
        params={"table": "orders"},
        outputs=(BATCH_OUT,),
        label="Orders",
    )
    renamed = Node.create(
        operator=OperatorRef("source.table"),
        instance_key="source-slot",
        params={"table": "orders"},
        outputs=(BATCH_OUT,),
        label="Pedidos",
    )
    duplicate = Node.create(
        operator=OperatorRef("source.table"),
        instance_key="second-source-slot",
        params={"table": "orders"},
        outputs=(BATCH_OUT,),
    )
    assert first.id == renamed.id
    assert first == renamed
    assert first.id != duplicate.id


def test_node_identity_requires_non_empty_instance_key() -> None:
    with pytest.raises(ValueError, match="instance_key"):
        Node.create(operator=OperatorRef("source.table"), instance_key="")


def test_node_param_returns_frozen_value_or_none() -> None:
    node = Node.create(
        operator=OperatorRef("source.table"),
        instance_key="source",
        params={"table": "orders"},
    )
    assert node.param("table") == "orders"
    assert node.param("missing") is None


def test_pipeline_canonicalizes_nodes_edges_and_serialization() -> None:
    source = _node("source", outputs=(BATCH_OUT,))
    sink = _node("sink", inputs=(BATCH_IN,))
    edge = Edge(source.id, "out", sink.id, "in")
    first = Pipeline(nodes=(sink, source), edges=(edge,), config=PipelineConfig("orders"))
    second = Pipeline(nodes=(source, sink), edges=(edge,), config=PipelineConfig("orders"))
    assert first == second
    assert first.to_json() == second.to_json()
    assert tuple(node.id for node in first.nodes) == tuple(sorted((source.id, sink.id)))


def test_pipeline_round_trip_preserves_typed_values_and_metadata() -> None:
    schema = SchemaRef("orders", "v1")
    source = Node.create(
        operator=OperatorRef("source.table", 2),
        instance_key="source",
        params={"table": "orders", "limits": [1, 2], "flags": {"safe": True}},
        outputs=(Port("out", "batch", schema),),
        origin=Origin("imported", "pipeline.py:12"),
        ownership="RECONCILED",
        label="Orders source",
    )
    sink = Node.create(
        operator=OperatorRef("sink.table"),
        instance_key="sink",
        inputs=(Port("in", "batch", schema),),
        ownership="USER",
    )
    pipeline = Pipeline((sink, source), (Edge(source.id, "out", sink.id, "in"),))
    restored = Pipeline.from_json(pipeline.to_json())
    assert restored == pipeline
    assert restored.to_data() == pipeline.to_data()


def test_empty_pipeline_round_trips() -> None:
    pipeline = Pipeline()
    assert Pipeline.from_data(pipeline.to_data()) == pipeline


def test_pipeline_rejects_duplicate_node_ids() -> None:
    node = _node("duplicate")
    with pytest.raises(ValueError, match="duplicate"):
        Pipeline((node, node))


def test_pipeline_rejects_edge_to_unknown_node() -> None:
    source = _node("source", outputs=(BATCH_OUT,))
    with pytest.raises(ValueError, match="unknown node"):
        Pipeline((source,), (Edge(source.id, "out", NodeId("missing"), "in"),))


def test_pipeline_rejects_missing_or_duplicate_port_name() -> None:
    source = _node("source", outputs=(BATCH_OUT, BATCH_OUT))
    sink = _node("sink", inputs=(BATCH_IN,))
    with pytest.raises(ValueError, match="exactly once"):
        Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))


def test_pipeline_rejects_port_kind_mismatch() -> None:
    source = _node("source", outputs=(STREAM_OUT,))
    sink = _node("sink", inputs=(BATCH_IN,))
    with pytest.raises(ValueError, match="port kinds"):
        Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))


def test_pipeline_rejects_schema_mismatch() -> None:
    source = _node("source", outputs=(Port("out", "batch", SchemaRef("a")),))
    sink = _node("sink", inputs=(Port("in", "batch", SchemaRef("b")),))
    with pytest.raises(ValueError, match="schemas"):
        Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))


def test_pipeline_allows_one_untyped_schema_endpoint() -> None:
    source = _node("source", outputs=(Port("out", "batch", SchemaRef("a")),))
    sink = _node("sink", inputs=(BATCH_IN,))
    pipeline = Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))
    assert pipeline.edges == (Edge(source.id, "out", sink.id, "in"),)


def test_pipeline_rejects_cycle() -> None:
    left = _node("left", inputs=(BATCH_IN,), outputs=(BATCH_OUT,))
    right = _node("right", inputs=(BATCH_IN,), outputs=(BATCH_OUT,))
    edges = (
        Edge(left.id, "out", right.id, "in"),
        Edge(right.id, "out", left.id, "in"),
    )
    with pytest.raises(ValueError, match="cycle"):
        Pipeline((left, right), edges)


@given(st.text(min_size=1), st.dictionaries(st.text(min_size=1), st.integers(), max_size=5))
def test_node_id_is_deterministic_for_arbitrary_json_params(
    instance_key: str, params: dict[str, int]
) -> None:
    first = Node.create(
        operator=OperatorRef("transform.property"), instance_key=instance_key, params=params
    )
    second = Node.create(
        operator=OperatorRef("transform.property"),
        instance_key=instance_key,
        params=dict(reversed(list(params.items()))),
    )
    assert first.id == second.id


@given(st.lists(st.text(min_size=1), unique=True, max_size=8))
def test_pipeline_order_is_canonical_for_arbitrary_insertion_order(keys: list[str]) -> None:
    nodes = tuple(_node(key) for key in keys)
    assert Pipeline(nodes).nodes == Pipeline(tuple(reversed(nodes))).nodes


def test_node_id_string_representation_is_value() -> None:
    assert str(NodeId("abc")) == "abc"
