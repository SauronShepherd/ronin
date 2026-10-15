from __future__ import annotations

import json

import pytest
from hypothesis import given
from hypothesis import strategies as st
from studio_core import Edge, Node, OperatorRef, Pipeline, Port, freeze_value

_JSON_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=40),
)
_JSON_VALUES = st.recursive(
    _JSON_SCALARS,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(min_size=1, max_size=12), children, max_size=5),
    ),
    max_leaves=12,
)


@given(_JSON_VALUES)
def test_property_pipeline_round_trip_is_canonical(value: object) -> None:
    node = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="round-trip",
        params={"value": value},
    )
    pipeline = Pipeline((node,))
    encoded = pipeline.to_json()
    restored = Pipeline.from_json(encoded)
    assert restored == pipeline
    assert restored.to_json() == encoded
    assert json.loads(encoded) == pipeline.to_data()


@given(st.one_of(st.binary(max_size=32), st.sets(st.integers(), max_size=5)))
def test_property_strict_json_rejects_non_json_values(value: object) -> None:
    with pytest.raises(TypeError, match="unsupported IR value type"):
        freeze_value(value)


@given(
    st.dictionaries(
        st.text(min_size=1, max_size=12),
        _JSON_SCALARS,
        min_size=1,
        max_size=8,
    ),
    st.text(max_size=30),
    st.text(max_size=30),
)
def test_property_node_identity_ignores_label_and_parameter_order(
    params: dict[str, object], first_label: str, second_label: str
) -> None:
    reversed_params = dict(reversed(tuple(params.items())))
    first = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="stable-node",
        params=params,
        label=first_label,
    )
    second = Node.create(
        operator=OperatorRef("transform.identity"),
        instance_key="stable-node",
        params=reversed_params,
        label=second_label,
    )
    assert first.id == second.id
    assert first == second


@given(st.permutations(("a", "b", "c", "d")))
def test_property_pipeline_output_is_deterministic_under_insertion_order(
    order: tuple[str, ...],
) -> None:
    nodes = {
        key: Node.create(
            operator=OperatorRef("transform.identity"),
            instance_key=key,
            inputs=(Port("in"),) if key != "a" else (),
            outputs=(Port("out"),) if key != "d" else (),
        )
        for key in ("a", "b", "c", "d")
    }
    edges = (
        Edge(nodes["a"].id, "out", nodes["b"].id, "in"),
        Edge(nodes["b"].id, "out", nodes["c"].id, "in"),
        Edge(nodes["c"].id, "out", nodes["d"].id, "in"),
    )
    expected = Pipeline(tuple(nodes.values()), edges).to_json()
    reordered_edges = tuple(reversed(edges))
    observed = Pipeline(tuple(nodes[key] for key in order), reordered_edges).to_json()
    assert observed == expected
