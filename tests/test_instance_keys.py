from dataclasses import FrozenInstanceError

import pytest
from studio_core import (
    Edge,
    InstanceAnchor,
    Node,
    NodeId,
    OperatorRef,
    Pipeline,
    Port,
    allocate_instance_keys,
)


def test_instance_anchor_is_immutable_validated_and_has_golden_keys() -> None:
    authoring = InstanceAnchor("authoring", "canvas:node-0007")
    imported = InstanceAnchor("import", "pipeline.py#element=source-12")

    assert (
        authoring.instance_key()
        == "9065a6d0033f42927122e0e32509884d22724abbd8ca44d961b6ab3f2dbbdc72"
    )
    assert (
        imported.instance_key()
        == "15c9ac5193ae24ea53d7898639676e021a6465b4ca1bacfb096561b5084e9db0"
    )
    with pytest.raises(FrozenInstanceError):
        authoring.reference = "changed"  # type: ignore[misc]

    with pytest.raises(ValueError, match="boundary"):
        InstanceAnchor("runtime", "stable")  # type: ignore[arg-type]
    for reference in ("", " spaced", "spaced "):
        with pytest.raises(ValueError, match="non-empty and trimmed"):
            InstanceAnchor("authoring", reference)
    with pytest.raises(ValueError, match="single-line"):
        InstanceAnchor("import", "file.py\nnode")


def test_instance_key_allocation_depends_only_on_unique_stable_anchors() -> None:
    left = InstanceAnchor("authoring", "canvas:left")
    right = InstanceAnchor("authoring", "canvas:right")
    first = allocate_instance_keys((left, right))
    reversed_keys = allocate_instance_keys((right, left))

    assert dict(zip((left, right), first, strict=True)) == dict(
        zip((right, left), reversed_keys, strict=True)
    )
    assert first[0] != first[1]
    with pytest.raises(ValueError, match="unique"):
        allocate_instance_keys((left, left))


def test_node_persists_instance_key_and_rejects_empty_direct_construction() -> None:
    anchor = InstanceAnchor("authoring", "canvas:orders")
    key = anchor.instance_key()
    node = Node.create(
        operator=OperatorRef("source.table"),
        instance_key=key,
        params={"table": "orders"},
        outputs=(Port("out"),),
        label="Orders",
    )
    data = Pipeline((node,)).to_data()

    assert data["nodes"][0]["instance_key"] == key  # type: ignore[index]
    restored = Pipeline.from_data(data)
    assert restored == Pipeline((node,))
    assert restored.nodes[0].instance_key == key

    with pytest.raises(ValueError, match="instance_key"):
        Node(NodeId("manual"), "", OperatorRef("source.table"))


def test_deserialization_verifies_node_identity_evidence() -> None:
    node = Node.create(
        operator=OperatorRef("source.table"),
        instance_key=InstanceAnchor("import", "legacy.json#node=source").instance_key(),
        params={"table": "orders"},
        outputs=(Port("out"),),
    )
    data = Pipeline((node,)).to_data()
    serialized_node = data["nodes"][0]  # type: ignore[index]
    serialized_node["id"] = "tampered"  # type: ignore[index]
    with pytest.raises(ValueError, match="does not match"):
        Pipeline.from_data(data)

    data = Pipeline((node,)).to_data()
    serialized_node = data["nodes"][0]  # type: ignore[index]
    serialized_node.pop("instance_key")  # type: ignore[union-attr]
    with pytest.raises(TypeError, match="instance_key"):
        Pipeline.from_data(data)


def test_symmetric_identical_nodes_remain_distinct_and_order_independent() -> None:
    source = Node.create(
        operator=OperatorRef("source.table"),
        instance_key=InstanceAnchor("authoring", "canvas:source").instance_key(),
        params={"table": "orders"},
        outputs=(Port("out"),),
    )
    branch_keys = allocate_instance_keys(
        (
            InstanceAnchor("authoring", "canvas:branch-a"),
            InstanceAnchor("authoring", "canvas:branch-b"),
        )
    )
    left = Node.create(
        operator=OperatorRef("transform.filter"),
        instance_key=branch_keys[0],
        params={"expression": "amount > 0"},
        inputs=(Port("in"),),
        outputs=(Port("out"),),
        label="Positive orders A",
    )
    right = Node.create(
        operator=OperatorRef("transform.filter"),
        instance_key=branch_keys[1],
        params={"expression": "amount > 0"},
        inputs=(Port("in"),),
        outputs=(Port("out"),),
        label="Positive orders B",
    )
    renamed_left = Node.create(
        operator=left.operator,
        instance_key=left.instance_key,
        params={"expression": "amount > 0"},
        inputs=left.inputs,
        outputs=left.outputs,
        label="Renamed",
    )
    edges = (
        Edge(source.id, "out", left.id, "in"),
        Edge(source.id, "out", right.id, "in"),
    )

    first = Pipeline((source, left, right), edges)
    second = Pipeline((right, source, left), tuple(reversed(edges)))

    assert left.id != right.id
    assert renamed_left.id == left.id
    assert first.to_json() == second.to_json()
    assert Pipeline.from_json(first.to_json()) == first
