import pytest
from studio_core import Node, NodeId, OperatorRef


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
