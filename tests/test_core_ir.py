import json
from dataclasses import FrozenInstanceError

import pytest
import studio_core.ir as ir
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
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


def _serialized_node() -> dict[str, object]:
    node = Node.create(
        operator=OperatorRef("source.table"),
        instance_key="serialized",
        params={"table": "orders"},
        outputs=(Port("out", "batch", SchemaRef("orders", "v1")),),
        origin=Origin("imported", "source.py:1"),
        ownership="RECONCILED",
        label="Orders",
    )
    return Pipeline((node,)).to_data()


def test_ir_objects_are_immutable() -> None:
    node_id = NodeId("a")
    with pytest.raises(FrozenInstanceError):
        node_id.value = "b"  # type: ignore[misc]


def test_operator_version_must_be_positive() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        OperatorRef("invalid", 0)
    with pytest.raises(ValueError, match="integer"):
        OperatorRef("invalid", True)


def test_freeze_value_is_canonical_hashable_and_round_trips() -> None:
    first = freeze_value({"b": [2, 1], "a": {"enabled": True}})
    second = freeze_value({"a": {"enabled": True}, "b": [2, 1]})
    assert first == second
    assert isinstance(first, FrozenMap)
    assert isinstance(dict(first.items)["b"], FrozenList)
    assert thaw_value(first) == {"a": {"enabled": True}, "b": [2, 1]}
    assert hash(first) == hash(second)


def test_freeze_value_rejects_non_string_mapping_keys_unsupported_and_nonfinite_values() -> None:
    with pytest.raises(TypeError, match="keys"):
        freeze_value({1: "invalid"})
    with pytest.raises(TypeError, match="unsupported"):
        freeze_value(object())
    assert freeze_value((1, True)) == FrozenList((1, True))
    for value in (b"bytes", bytearray(b"bytearray")):
        with pytest.raises(TypeError, match="unsupported"):
            freeze_value(value)
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match=r"^IR float values must be finite$") as error:
            freeze_value(value)
        assert str(error.value) == "IR float values must be finite"

    with pytest.raises(TypeError) as error:
        freeze_value({1: "invalid"})
    assert str(error.value) == "IR mapping keys must be strings"


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


def test_node_identity_distinguishes_python_numeric_types_consistently() -> None:
    operator = OperatorRef("transform.identity")
    integer = Node.create(operator=operator, instance_key="k", params={"x": 1})
    floating = Node.create(operator=operator, instance_key="k", params={"x": 1.0})
    boolean = Node.create(operator=operator, instance_key="k", params={"x": True})
    zero = Node.create(operator=operator, instance_key="k", params={"x": 0.0})
    negative_zero = Node.create(operator=operator, instance_key="k", params={"x": -0.0})

    assert integer != floating
    assert integer.id != floating.id
    assert integer != boolean
    assert integer.id != boolean.id
    assert zero != negative_zero
    assert zero.id != negative_zero.id


def test_node_identity_includes_every_semantic_component() -> None:
    base = Node.create(
        operator=OperatorRef("transform.identity", 1),
        instance_key="semantic",
        params={"x": 1},
        inputs=(Port("in", "batch", SchemaRef("input", "v1")),),
        outputs=(Port("out", "batch", SchemaRef("output", "v1")),),
    )
    variants = (
        Node.create(
            operator=OperatorRef("transform.other", 1),
            instance_key="semantic",
            params={"x": 1},
            inputs=base.inputs,
            outputs=base.outputs,
        ),
        Node.create(
            operator=OperatorRef("transform.identity", 2),
            instance_key="semantic",
            params={"x": 1},
            inputs=base.inputs,
            outputs=base.outputs,
        ),
        Node.create(
            operator=base.operator,
            instance_key="semantic",
            params={"x": 2},
            inputs=base.inputs,
            outputs=base.outputs,
        ),
        Node.create(
            operator=base.operator,
            instance_key="semantic",
            params={"x": 1},
            inputs=(Port("changed", "batch", SchemaRef("input", "v1")),),
            outputs=base.outputs,
        ),
        Node.create(
            operator=base.operator,
            instance_key="semantic",
            params={"x": 1},
            inputs=base.inputs,
            outputs=(Port("out", "stream", SchemaRef("output", "v1")),),
        ),
    )
    assert all(variant.id != base.id for variant in variants)


def test_node_semantic_payload_names_every_identity_component() -> None:
    payload = ir._node_semantic_payload(
        OperatorRef("transform.identity", 2),
        (("threshold", 3),),
        (Port("input", "batch"),),
        (Port("output", "stream"),),
    )
    assert payload == (
        '{"inputs":[{"kind":"batch","name":"input","schema":null}],'
        '"operator":{"name":"transform.identity","version":2},'
        '"outputs":[{"kind":"stream","name":"output","schema":null}],'
        '"params":{"threshold":3}}'
    )


def test_node_direct_constructor_rejects_mismatched_identity() -> None:
    with pytest.raises(ValueError, match="node id"):
        Node(NodeId("deadbeef"), "k", OperatorRef("transform.identity"))


def test_node_ports_have_total_canonical_order_with_optional_schema() -> None:
    node = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="ports",
        inputs=(Port("a", "batch", SchemaRef("s")), Port("a", "batch", None)),
    )
    assert node.inputs == (
        Port("a", "batch", None),
        Port("a", "batch", SchemaRef("s")),
    )


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


def test_pipeline_json_is_strict_and_round_trip_preserves_typed_values_and_metadata() -> None:
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
    payload = pipeline.to_json()
    restored = Pipeline.from_json(payload)
    assert restored == pipeline
    assert restored.to_data() == pipeline.to_data()
    json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def test_empty_pipeline_round_trips() -> None:
    pipeline = Pipeline()
    assert Pipeline.from_data(pipeline.to_data()) == pipeline


def test_pipeline_rejects_duplicate_node_ids() -> None:
    node = _node("duplicate")
    with pytest.raises(ValueError, match=r"^duplicate node id$"):
        Pipeline((node, node))


def test_pipeline_rejects_duplicate_edges() -> None:
    source = _node("source", outputs=(BATCH_OUT,))
    sink = _node("sink", inputs=(BATCH_IN,))
    edge = Edge(source.id, "out", sink.id, "in")
    with pytest.raises(ValueError, match=r"^duplicate edge$"):
        Pipeline((source, sink), (edge, edge))


def test_pipeline_rejects_edge_to_unknown_node() -> None:
    source = _node("source", outputs=(BATCH_OUT,))
    with pytest.raises(ValueError, match=r"^edge references unknown node$"):
        Pipeline((source,), (Edge(source.id, "out", NodeId("missing"), "in"),))
    with pytest.raises(ValueError, match=r"^edge references unknown node$"):
        Pipeline((source,), (Edge(NodeId("missing"), "out", source.id, "in"),))


def test_pipeline_rejects_missing_or_duplicate_port_name() -> None:
    source = _node("source", outputs=(BATCH_OUT, BATCH_OUT))
    sink = _node("sink", inputs=(BATCH_IN,))
    with pytest.raises(ValueError, match=r"^port 'out' does not exist exactly once$"):
        Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))


def test_pipeline_rejects_port_kind_mismatch() -> None:
    source = _node("source", outputs=(STREAM_OUT,))
    sink = _node("sink", inputs=(BATCH_IN,))
    with pytest.raises(ValueError, match=r"^edge connects incompatible port kinds$"):
        Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))


def test_pipeline_rejects_schema_mismatch() -> None:
    source = _node("source", outputs=(Port("out", "batch", SchemaRef("a")),))
    sink = _node("sink", inputs=(Port("in", "batch", SchemaRef("b")),))
    with pytest.raises(ValueError, match=r"^edge connects incompatible schemas$"):
        Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))


def test_pipeline_allows_one_untyped_schema_endpoint() -> None:
    source = _node("source", outputs=(Port("out", "batch", SchemaRef("a")),))
    sink = _node("sink", inputs=(BATCH_IN,))
    pipeline = Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),))
    assert pipeline.edges == (Edge(source.id, "out", sink.id, "in"),)

    untyped_source = _node("untyped-source", outputs=(BATCH_OUT,))
    typed_sink = _node("typed-sink", inputs=(Port("in", "batch", SchemaRef("a")),))
    assert Pipeline(
        (untyped_source, typed_sink),
        (Edge(untyped_source.id, "out", typed_sink.id, "in"),),
    ).edges


def test_pipeline_rejects_cycle() -> None:
    left = _node("left", inputs=(BATCH_IN,), outputs=(BATCH_OUT,))
    right = _node("right", inputs=(BATCH_IN,), outputs=(BATCH_OUT,))
    edges = (
        Edge(left.id, "out", right.id, "in"),
        Edge(right.id, "out", left.id, "in"),
    )
    with pytest.raises(ValueError, match=r"^pipeline contains a cycle$"):
        Pipeline((left, right), edges)


def test_pipeline_validates_converging_dag_before_target_is_ready() -> None:
    source = _node("root", outputs=(BATCH_OUT,))
    left = _node("left-branch", inputs=(BATCH_IN,), outputs=(BATCH_OUT,))
    right = _node("right-branch", inputs=(BATCH_IN,), outputs=(BATCH_OUT,))
    sink = _node("join", inputs=(Port("left"), Port("right")))
    edges = (
        Edge(source.id, "out", left.id, "in"),
        Edge(source.id, "out", right.id, "in"),
        Edge(left.id, "out", sink.id, "left"),
        Edge(right.id, "out", sink.id, "right"),
    )
    assert len(Pipeline((source, left, right, sink), edges).edges) == 4


def test_from_json_rejects_non_object_payload() -> None:
    with pytest.raises(TypeError, match="pipeline"):
        Pipeline.from_json("[]")


def test_from_data_rejects_invalid_top_level_shapes() -> None:
    cases = (
        ({"config": [], "nodes": [], "edges": []}, TypeError),
        ({"config": {1: "main"}, "nodes": [], "edges": []}, TypeError),
        ({"config": {"name": 1}, "nodes": [], "edges": []}, TypeError),
        ({"config": {"name": "main"}, "nodes": 1, "edges": []}, TypeError),
        ({"config": {"name": "main"}, "nodes": [], "edges": "bad"}, TypeError),
    )
    for payload, error in cases:
        with pytest.raises(error):
            Pipeline.from_data(payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("operator", None, "operator must be an object with string keys"),
        ("params", None, "params must be an object with string keys"),
        ("inputs", None, "inputs must be an array"),
        ("outputs", None, "outputs must be an array"),
        ("origin", None, "origin must be an object with string keys"),
        ("ownership", None, "ownership must be a string"),
        ("instance_key", None, "instance_key must be a string"),
        ("id", None, "id must be a string"),
    ],
)
def test_from_data_rejects_missing_required_node_fields(
    field: str, value: object, message: str
) -> None:
    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    node[field] = value  # type: ignore[index]
    with pytest.raises((TypeError, ValueError), match=message):
        Pipeline.from_data(data)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("operator", [], "operator must be an object with string keys"),
        ("params", [], "params must be an object with string keys"),
        ("inputs", "bad", "inputs must be an array"),
        ("outputs", "bad", "outputs must be an array"),
        ("origin", [], "origin must be an object with string keys"),
        ("ownership", 1, "ownership must be a string"),
        ("instance_key", 1, "instance_key must be a string"),
        ("id", 1, "id must be a string"),
    ],
)
def test_from_data_rejects_invalid_required_node_field_shapes(
    field: str, value: object, message: str
) -> None:
    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    node[field] = value  # type: ignore[index]
    with pytest.raises((TypeError, ValueError), match=message):
        Pipeline.from_data(data)


def test_from_data_rejects_invalid_node_enums_and_metadata_types() -> None:
    for field, value, error, match in (
        ("ownership", "INVALID", ValueError, "invalid ownership"),
        ("label", 7, TypeError, "label must be a string or null"),
    ):
        data = _serialized_node()
        node = data["nodes"][0]  # type: ignore[index]
        node[field] = value  # type: ignore[index]
        with pytest.raises(error, match=match):
            Pipeline.from_data(data)

    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    origin = node["origin"]  # type: ignore[index]
    origin["view"] = "INVALID"  # type: ignore[index]
    with pytest.raises(ValueError, match="invalid origin view"):
        Pipeline.from_data(data)

    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    origin = node["origin"]  # type: ignore[index]
    origin["reference"] = 9  # type: ignore[index]
    with pytest.raises(TypeError, match="origin.reference must be a string or null"):
        Pipeline.from_data(data)


def test_from_data_rejects_invalid_operator_port_and_schema_types() -> None:
    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    operator = node["operator"]  # type: ignore[index]
    operator["version"] = True  # type: ignore[index]
    with pytest.raises(TypeError, match="operator.version must be an integer"):
        Pipeline.from_data(data)

    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    output = node["outputs"][0]  # type: ignore[index]
    output["kind"] = "invalid"  # type: ignore[index]
    with pytest.raises(ValueError, match="port.kind must be batch or stream"):
        Pipeline.from_data(data)

    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    output = node["outputs"][0]  # type: ignore[index]
    schema = output["schema"]  # type: ignore[index]
    schema["version"] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match="schema.version must be a string or null"):
        Pipeline.from_data(data)

    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    output = node["outputs"][0]  # type: ignore[index]
    output["schema"] = []  # type: ignore[index]
    with pytest.raises(TypeError, match="schema must be an object with string keys"):
        Pipeline.from_data(data)


def test_from_data_binds_nested_error_context_and_required_operator_fields() -> None:
    node = Node.create(
        operator=OperatorRef("transform.identity", 2),
        instance_key="nested-errors",
        inputs=(Port("in"),),
        outputs=(Port("out"),),
    )
    data = Pipeline((node,)).to_data()
    node_data = data["nodes"][0]  # type: ignore[index]

    for field, value, message in (
        ("name", None, "operator.name must be a string"),
        ("version", None, "operator.version must be an integer"),
    ):
        mutated = Pipeline((node,)).to_data()
        operator = mutated["nodes"][0]["operator"]  # type: ignore[index]
        operator[field] = value  # type: ignore[index]
        with pytest.raises(TypeError, match=message):
            Pipeline.from_data(mutated)

    for field, message in (("inputs", "input"), ("outputs", "output")):
        mutated = Pipeline((node,)).to_data()
        mutated["nodes"][0][field] = [None]  # type: ignore[index]
        with pytest.raises(TypeError, match=f"{message} must be an object with string keys"):
            Pipeline.from_data(mutated)

    node_data["id"] = "wrong-id"  # type: ignore[index]
    with pytest.raises(
        ValueError, match="^node id does not match semantic content and instance_key$"
    ):
        Pipeline.from_data(data)


@pytest.mark.parametrize("ownership", ["GRAPH", "USER", "RECONCILED"])
@pytest.mark.parametrize("origin_view", ["graph", "notebook", "imported", "system"])
def test_from_data_accepts_every_declared_node_metadata_variant(
    ownership: str, origin_view: str
) -> None:
    node = Node.create(
        operator=OperatorRef("source.table", 1),
        instance_key=f"{ownership}-{origin_view}",
        params={},
        origin=Origin(origin_view, None),  # type: ignore[arg-type]
        ownership=ownership,  # type: ignore[arg-type]
        label=None,
    )
    restored = Pipeline.from_data(Pipeline((node,)).to_data())
    assert restored.nodes == (node,)


def test_from_data_preserves_optional_schema_and_frozen_parameters() -> None:
    node = Node.create(
        operator=OperatorRef("transform.identity", 2),
        instance_key="optional-schema",
        params={"nested": {"enabled": True, "values": [1, 2]}},
        inputs=(Port("in", "batch"),),
        outputs=(Port("out", "stream"),),
        origin=Origin("notebook", "cell-1"),
        ownership="USER",
        label="optional",
    )
    restored = Pipeline.from_data(Pipeline((node,)).to_data()).nodes[0]
    assert restored.params == node.params
    assert restored.inputs[0].schema is None
    assert restored.outputs[0].schema is None


def test_from_data_rejects_semantic_id_mismatch() -> None:
    data = _serialized_node()
    node = data["nodes"][0]  # type: ignore[index]
    node["id"] = "wrong-id"  # type: ignore[index]
    with pytest.raises(ValueError, match="semantic content"):
        Pipeline.from_data(data)


def test_from_data_rejects_invalid_nested_collection_shapes() -> None:
    for field, value, match in (
        ("operator", [], "operator"),
        ("params", [], "params"),
        ("inputs", "bad", "inputs"),
        ("outputs", 3, "outputs"),
        ("origin", [], "origin"),
    ):
        data = _serialized_node()
        node = data["nodes"][0]  # type: ignore[index]
        node[field] = value  # type: ignore[index]
        with pytest.raises(TypeError, match=match):
            Pipeline.from_data(data)


def test_from_data_rejects_invalid_edge_field_type() -> None:
    source = _node("edge-source", outputs=(BATCH_OUT,))
    sink = _node("edge-sink", inputs=(BATCH_IN,))
    data = Pipeline((source, sink), (Edge(source.id, "out", sink.id, "in"),)).to_data()
    edge = data["edges"][0]  # type: ignore[index]
    edge["source_port"] = 7  # type: ignore[index]
    with pytest.raises(TypeError, match="edge.source_port"):
        Pipeline.from_data(data)


@given(
    st.text(min_size=1),
    st.dictionaries(
        st.text(min_size=1), st.integers(min_value=-(2**53 - 1), max_value=2**53 - 1), max_size=5
    ),
)
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
    assert first == second


@settings(
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.lists(st.text(min_size=1), unique=True, max_size=8))
def test_pipeline_order_is_canonical_for_arbitrary_insertion_order(keys: list[str]) -> None:
    nodes = tuple(_node(key) for key in keys)
    assert Pipeline(nodes).nodes == Pipeline(tuple(reversed(nodes))).nodes


def test_node_id_string_representation_is_value() -> None:
    assert str(NodeId("abc")) == "abc"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ({"name": "orders"}, SchemaRef("orders")),
        ({"name": "orders", "version": "v1"}, SchemaRef("orders", "v1")),
    ],
)
def test_ir_schema_parser_handles_optional_version_and_null_schema(
    value: object, expected: SchemaRef | None
) -> None:
    assert ir._schema_from_data(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"name": None}, "schema.name"),
        ({"name": "orders", "version": 1}, "schema.version"),
        ([], "schema"),
    ],
)
def test_ir_schema_parser_rejects_invalid_shapes(value: object, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        ir._schema_from_data(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"name": "in", "kind": "batch", "schema": None}, Port("in")),
        (
            {"name": "events", "kind": "stream", "schema": {"name": "event", "version": "v1"}},
            Port("events", "stream", SchemaRef("event", "v1")),
        ),
    ],
)
def test_ir_port_parser_preserves_kind_and_schema(value: object, expected: Port) -> None:
    assert ir._port_from_data(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        {"name": None, "kind": "batch", "schema": None},
        {"name": "out", "kind": "batch", "schema": 1},
        {"name": "out", "kind": "invalid", "schema": None},
        {"name": "out", "kind": None, "schema": None},
    ],
)
def test_ir_port_parser_rejects_invalid_name_kind_and_schema(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        ir._port_from_data(value)  # type: ignore[arg-type]


def test_ir_edge_parser_reads_all_fields_and_rejects_each_wrong_type() -> None:
    edge_data = {
        "source": "source",
        "source_port": "out",
        "target": "target",
        "target_port": "in",
    }
    edge = ir._edge_from_data(edge_data)
    assert edge == Edge(NodeId("source"), "out", NodeId("target"), "in")
    for field in edge_data:
        invalid = dict(edge_data)
        invalid[field] = None
        with pytest.raises(TypeError, match=f"edge.{field}"):
            ir._edge_from_data(invalid)


def test_ir_node_parser_preserves_all_optional_and_semantic_fields() -> None:
    node = Node.create(
        operator=OperatorRef("source.table", 3),
        instance_key="node-parser",
        params={"table": "orders", "flags": {"enabled": True}},
        inputs=(Port("in", "batch", SchemaRef("orders", "v1")),),
        outputs=(Port("out", "stream"),),
        origin=Origin("notebook", "cell-7"),
        ownership="USER",
        label="Orders",
    )
    restored = ir._node_from_data(Pipeline((node,)).to_data()["nodes"][0])  # type: ignore[arg-type]
    assert restored == node
    assert restored.operator == OperatorRef("source.table", 3)
    assert restored.origin == Origin("notebook", "cell-7")
    assert restored.ownership == "USER"
    assert restored.label == "Orders"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operator", {"name": "source.table", "version": True}),
        ("operator", {"name": None, "version": 1}),
        ("params", []),
        ("inputs", [None]),
        ("outputs", [None]),
        ("origin", {"view": "notebook", "reference": 1}),
        ("ownership", "invalid"),
        ("instance_key", ""),
    ],
)
def test_ir_node_parser_rejects_semantic_field_mutations(field: str, value: object) -> None:
    data = _serialized_node()
    node_data = data["nodes"][0]  # type: ignore[index]
    node_data[field] = value  # type: ignore[index]
    with pytest.raises((TypeError, ValueError)):
        ir._node_from_data(node_data)  # type: ignore[arg-type]


def test_ir_require_helpers_distinguish_mapping_sequence_string_and_bytes() -> None:
    mapping = {"key": "value"}
    sequence = ["a", "b"]
    assert ir._require_mapping(mapping, "mapping") == mapping
    assert ir._require_sequence(sequence, "sequence") == sequence
    for value in (None, [], {1: "value"}, "text", b"bytes", bytearray(b"bytes")):
        with pytest.raises(TypeError):
            ir._require_mapping(value, "mapping")
    for value in (None, {}, "text", b"bytes", bytearray(b"bytes")):
        with pytest.raises(TypeError):
            ir._require_sequence(value, "sequence")
