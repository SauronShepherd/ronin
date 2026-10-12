import math

import pytest
from studio_core import FrozenList, FrozenMap, Node, NodeId, OperatorRef, Port, SchemaRef
from studio_core.ir import (
    _canonical_json,
    _edge_from_data,
    _frozen_comparison_key,
    _node_from_data,
    _node_semantic_payload,
    _port_from_data,
    _port_sort_key,
    _require_mapping,
    _require_sequence,
    _schema_from_data,
)


def test_node_param_lookup_does_not_return_neighbouring_sorted_parameter() -> None:
    node = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="lookup-boundaries",
        params={"alpha": 1, "omega": 2},
    )

    assert node.param("alpha") == 1
    assert node.param("omega") == 2
    for missing in ("", "aardvark", "middle", "zzzz"):
        assert node.param(missing) is None


def test_node_comparison_and_hash_cover_null_and_string_values() -> None:
    first = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="typed-values",
        params={"optional": None, "name": "orders"},
    )
    second = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="typed-values",
        params={"name": "orders", "optional": None},
    )

    assert first == second
    assert hash(first) == hash(second)
    assert first != object()


def test_direct_node_constructor_rejects_duplicate_parameter_names_before_identity_check() -> None:
    with pytest.raises(ValueError, match="parameter names must be unique"):
        Node(
            NodeId("synthetic"),
            "duplicate-params",
            OperatorRef("transform.identity"),
            params=(("x", 1), ("x", 2)),
        )


def test_typed_identity_encoding_is_stable_for_every_frozen_value_kind() -> None:
    assert _frozen_comparison_key(None) == ("null",)
    assert _frozen_comparison_key(False) == ("bool", False)
    assert _frozen_comparison_key(True) == ("bool", True)
    assert _frozen_comparison_key(7) == ("int", 7)
    assert _frozen_comparison_key(-3) == ("int", -3)
    assert _frozen_comparison_key(1.5) == ("float", (1.5).hex())
    assert _frozen_comparison_key(-0.0) == ("float", (-0.0).hex())
    assert _frozen_comparison_key("orders") == ("str", "orders")
    assert _frozen_comparison_key(FrozenList((1, True, "x"))) == (
        "list",
        (("int", 1), ("bool", True), ("str", "x")),
    )
    assert _frozen_comparison_key(FrozenMap((("a", 1), ("b", None)))) == (
        "map",
        (("a", ("int", 1)), ("b", ("null",))),
    )


def test_port_order_key_is_stable_across_optional_schema_shapes() -> None:
    assert _port_sort_key(Port("input", "batch")) == ("input", "batch", "", "")
    assert _port_sort_key(Port("input", "stream", SchemaRef("orders"))) == (
        "input",
        "stream",
        "orders",
        "",
    )
    assert _port_sort_key(Port("input", "batch", SchemaRef("orders", "v2"))) == (
        "input",
        "batch",
        "orders",
        "v2",
    )


def test_canonical_json_encoding_is_compact_sorted_unicode_and_strict() -> None:
    assert _canonical_json({"z": 1, "a": "ñ"}) == '{"a":"ñ","z":1}'
    assert _canonical_json([True, None, 1.5]) == "[true,null,1.5]"
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="Out of range float values"):
            _canonical_json({"value": value})


@pytest.mark.parametrize("value", [[], "bad", 1, {"version": 1}])
def test_schema_from_data_rejects_non_object_or_invalid_version(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _schema_from_data(value)


def test_schema_from_data_preserves_null_and_string_versions() -> None:
    assert _schema_from_data(None) is None
    assert _schema_from_data({"name": "orders", "version": None}).version is None
    assert _schema_from_data({"name": "orders", "version": "v1"}).version == "v1"


@pytest.mark.parametrize("key", ["name"])
def test_schema_from_data_requires_each_declared_field(key: str) -> None:
    value: dict[str, object] = {"name": "orders", "version": "v1"}
    del value[key]
    with pytest.raises(TypeError, match=f"schema.{key}"):
        _schema_from_data(value)


@pytest.mark.parametrize("kind", ["batch", "stream"])
def test_port_from_data_accepts_declared_kinds_and_optional_schema(kind: str) -> None:
    port = _port_from_data({"name": "port", "kind": kind, "schema": None})
    assert port.name == "port"
    assert port.kind == kind
    assert port.schema is None


def test_port_from_data_rejects_missing_name_and_invalid_kind() -> None:
    with pytest.raises(TypeError, match="port.name"):
        _port_from_data({"kind": "batch", "schema": None})
    with pytest.raises(ValueError, match="port.kind"):
        _port_from_data({"name": "port", "kind": "row", "schema": None})


@pytest.mark.parametrize("key", ["name", "kind"])
def test_port_from_data_requires_each_declared_field(key: str) -> None:
    value: dict[str, object] = {"name": "port", "kind": "batch", "schema": None}
    del value[key]
    with pytest.raises((TypeError, ValueError), match=f"port.{key}|schema"):
        _port_from_data(value)


def test_node_semantic_payload_is_explicit_and_identity_bearing() -> None:
    payload = _node_semantic_payload(
        OperatorRef("transform.identity", 2),
        (("table", "orders"), ("limit", 10)),
        (Port("in", "batch", SchemaRef("orders", "v1")),),
        (Port("out", "stream"),),
    )
    assert payload == (
        '{"inputs":[{"kind":"batch","name":"in","schema":{"name":"orders",'
        '"version":"v1"}}],"operator":{"name":"transform.identity","version":2},'
        '"outputs":[{"kind":"stream","name":"out","schema":null}],'
        '"params":{"limit":10,"table":"orders"}}'
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"version": "v1"}, "schema.name must be a string"),
        ({"name": "orders", "version": 1}, "schema.version must be a string or null"),
    ],
)
def test_schema_parser_errors_are_stable(value: object, message: str) -> None:
    with pytest.raises(TypeError) as error:
        _schema_from_data(value)
    assert str(error.value) == message


def test_schema_and_port_parser_diagnostics_are_not_generic() -> None:
    with pytest.raises(TypeError) as schema_error:
        _schema_from_data({"name": "orders", "version": 1})
    assert str(schema_error.value) == "schema.version must be a string or null"

    with pytest.raises(TypeError) as port_error:
        _port_from_data({"name": None, "kind": "batch", "schema": None})
    assert str(port_error.value) == "port.name must be a string"


@pytest.mark.parametrize(
    ("value", "error_type", "message"),
    [
        ({"kind": "batch", "schema": None}, TypeError, "port.name must be a string"),
        (
            {"name": "p", "kind": "row", "schema": None},
            ValueError,
            "port.kind must be batch or stream",
        ),
    ],
)
def test_port_parser_errors_are_stable(
    value: object, error_type: type[Exception], message: str
) -> None:
    with pytest.raises(error_type) as error:
        _port_from_data(value)  # type: ignore[arg-type]
    assert str(error.value) == message


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ownership", "INVALID", "invalid ownership"),
        ("origin", {"view": "invalid", "reference": None}, "invalid origin view"),
        ("origin", {"view": "graph", "reference": 1}, "origin.reference must be a string or null"),
        ("label", 1, "label must be a string or null"),
    ],
)
def test_node_parser_rejects_invalid_metadata_with_stable_messages(
    field: str, value: object, message: str
) -> None:
    node = Node.create(operator=OperatorRef("source.table"), instance_key="node")
    data = {
        "id": node.id.value,
        "instance_key": node.instance_key,
        "operator": {"name": node.operator.name, "version": node.operator.version},
        "params": {},
        "inputs": [],
        "outputs": [],
        "origin": {"view": "system", "reference": None},
        "ownership": "GRAPH",
        "label": None,
    }
    data[field] = value
    with pytest.raises((TypeError, ValueError)) as error:
        _node_from_data(data)
    assert str(error.value) == message


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("source", "edge.source must be a string"),
        ("source_port", "edge.source_port must be a string"),
        ("target", "edge.target must be a string"),
        ("target_port", "edge.target_port must be a string"),
    ],
)
def test_edge_parser_required_field_messages_are_stable(field: str, message: str) -> None:
    value: dict[str, object] = {
        "source": "source",
        "source_port": "out",
        "target": "target",
        "target_port": "in",
    }
    value[field] = None
    with pytest.raises(TypeError) as error:
        _edge_from_data(value)
    assert str(error.value) == message


def test_edge_parser_diagnostics_name_each_required_field() -> None:
    value: dict[str, object] = {
        "source": "source",
        "source_port": "out",
        "target": "target",
        "target_port": "in",
    }
    for field in value:
        invalid = dict(value)
        invalid[field] = None
        with pytest.raises(TypeError) as error:
            _edge_from_data(invalid)
        assert str(error.value) == f"edge.{field} must be a string"


@pytest.mark.parametrize("key", ["source", "source_port", "target", "target_port"])
def test_edge_parser_requires_each_declared_field(key: str) -> None:
    value: dict[str, object] = {
        "source": "source",
        "source_port": "out",
        "target": "target",
        "target_port": "in",
    }
    del value[key]
    with pytest.raises(TypeError, match=f"edge.{key}"):
        _edge_from_data(value)


def test_ir_shape_helpers_accept_tuples_and_reject_non_array_collections() -> None:
    mapping = {"name": "value"}
    sequence = ("a", "b")
    assert _require_mapping(mapping, "mapping") == mapping
    assert _require_mapping(mapping, "mapping") is mapping
    assert _require_sequence(sequence, "sequence") == sequence
    assert _require_sequence(sequence, "sequence") is sequence
    for value in (set(), frozenset(), iter(("a",))):
        with pytest.raises(TypeError, match="array"):
            _require_sequence(value, "sequence")
