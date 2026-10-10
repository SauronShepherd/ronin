import math

import pytest
from studio_core import FrozenList, FrozenMap, Node, NodeId, OperatorRef, Port, SchemaRef
from studio_core.ir import (
    _canonical_json,
    _frozen_comparison_key,
    _port_from_data,
    _port_sort_key,
    _schema_from_data,
)


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
