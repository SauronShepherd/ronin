import json
from pathlib import Path

import pytest
from studio_core import (
    Node,
    NodeId,
    OperatorCatalog,
    OperatorContract,
    OperatorParameter,
    OperatorPort,
    OperatorRef,
    Port,
    builtin_operator_catalog,
    operator_parameter_value,
    validate_operator_node,
)


def _node(
    ref: OperatorRef,
    *,
    params: dict[str, object] | None = None,
    inputs: tuple[Port, ...] = (),
    outputs: tuple[Port, ...] = (),
) -> Node:
    return Node.create(
        operator=ref,
        instance_key="test",
        params=params,
        inputs=inputs,
        outputs=outputs,
    )


def test_operator_primitives_reject_invalid_metadata() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        OperatorPort("")
    with pytest.raises(ValueError, match="line breaks"):
        OperatorPort("in", "bad\nkind")
    with pytest.raises(ValueError, match="cardinality"):
        OperatorPort("in", cardinality="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="parameter name"):
        OperatorParameter(" ")
    with pytest.raises(ValueError, match="unsupported"):
        OperatorParameter("value", "invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at most 500"):
        OperatorPort("x" * 501)


def test_operator_contract_canonicalizes_and_rejects_conflicts() -> None:
    contract = OperatorContract(
        OperatorRef("transform.test"),
        "Test",
        "transforms",
        inputs=(OperatorPort("z"), OperatorPort("a", optional=True)),
        parameters=(OperatorParameter("z"), OperatorParameter("a", "string")),
        modes=("stream", "batch", "batch"),
        required_capabilities=("engine.sql", "engine.compute"),
        forbidden_capabilities=("feature.legacy",),
        documentation_key="operator.transform.test",
    )
    assert [port.name for port in contract.inputs] == ["a", "z"]
    assert [parameter.name for parameter in contract.parameters] == ["a", "z"]
    assert contract.modes == ("batch", "stream")
    assert contract.required_capabilities == ("engine.compute", "engine.sql")
    assert contract.to_data()["documentation_key"] == "operator.transform.test"

    with pytest.raises(ValueError, match="input port names"):
        OperatorContract(
            OperatorRef("duplicate.inputs"),
            "Duplicate",
            "test",
            inputs=(OperatorPort("in"), OperatorPort("in")),
        )
    with pytest.raises(ValueError, match="output port names"):
        OperatorContract(
            OperatorRef("duplicate.outputs"),
            "Duplicate",
            "test",
            outputs=(OperatorPort("out"), OperatorPort("out")),
        )
    with pytest.raises(ValueError, match="parameter names"):
        OperatorContract(
            OperatorRef("duplicate.params"),
            "Duplicate",
            "test",
            parameters=(OperatorParameter("x"), OperatorParameter("x")),
        )
    with pytest.raises(ValueError, match="modes must be non-empty"):
        OperatorContract(OperatorRef("no.mode"), "No Mode", "test", modes=())
    with pytest.raises(ValueError, match="mode must be"):
        OperatorContract(
            OperatorRef("bad.mode"),
            "Bad Mode",
            "test",
            modes=("invalid",),  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="unique"):
        OperatorContract(
            OperatorRef("duplicate.capability"),
            "Duplicate Capability",
            "test",
            required_capabilities=("engine.sql", "engine.sql"),
        )
    with pytest.raises(ValueError, match="both required and forbidden"):
        OperatorContract(
            OperatorRef("capability.conflict"),
            "Conflict",
            "test",
            required_capabilities=("engine.sql",),
            forbidden_capabilities=("engine.sql",),
        )
    with pytest.raises(ValueError, match="documentation key"):
        OperatorContract(
            OperatorRef("bad.docs"),
            "Bad Docs",
            "test",
            documentation_key=" ",
        )


def test_catalog_is_version_aware_canonical_and_serializable() -> None:
    v1 = OperatorContract(OperatorRef("x", 1), "X1", "test")
    v2 = OperatorContract(OperatorRef("x", 2), "X2", "test")
    other = OperatorContract(OperatorRef("a", 1), "A", "test")
    catalog = OperatorCatalog((v2, other, v1))
    assert [item.ref for item in catalog.operators] == [other.ref, v1.ref, v2.ref]
    assert catalog.get(v1.ref) == v1
    assert catalog.get(OperatorRef("missing")) is None
    assert catalog.latest("x") == v2
    assert catalog.latest("missing") is None
    assert json.loads(catalog.to_json()) == catalog.to_data()
    with pytest.raises(ValueError, match="unique"):
        OperatorCatalog((v1, v1))


def test_builtin_operator_catalog_matches_golden_seed_and_is_portable() -> None:
    catalog = builtin_operator_catalog()
    projection = [
        {
            "category": operator.category,
            "name": operator.ref.name,
            "version": operator.ref.version,
        }
        for operator in catalog.operators
    ]
    expected = json.loads(Path("tests/golden/operator_seed_refs.json").read_text(encoding="utf-8"))
    assert projection == expected
    assert catalog.get(OperatorRef("transform.join")) is not None
    assert "spark" not in catalog.to_json().lower()
    assert "databricks" not in catalog.to_json().lower()
    assert "fabric" not in catalog.to_json().lower()


def test_node_validation_reports_missing_unknown_and_bad_parameters() -> None:
    contract = OperatorContract(
        OperatorRef("transform.contract"),
        "Contract",
        "test",
        inputs=(OperatorPort("in"),),
        outputs=(OperatorPort("out"),),
        parameters=(
            OperatorParameter("expression", "expression", required=True),
            OperatorParameter("limit", "integer"),
        ),
    )
    catalog = OperatorCatalog((contract,))
    node = _node(
        contract.ref,
        params={"limit": "ten", "extra": True},
        inputs=(Port("in"),),
        outputs=(Port("out"),),
    )
    violations = validate_operator_node(node, catalog)
    assert [(item.code, item.path) for item in violations] == [
        ("RONIN-OP-002", "params.expression"),
        ("RONIN-OP-003", "params.limit"),
        ("RONIN-OP-004", "params.extra"),
    ]
    missing_contract = validate_operator_node(_node(OperatorRef("unknown")), catalog)
    assert missing_contract[0].code == "RONIN-OP-001"


def test_node_validation_checks_ports_and_modes() -> None:
    contract = OperatorContract(
        OperatorRef("batch.only"),
        "Batch Only",
        "test",
        inputs=(OperatorPort("required"), OperatorPort("optional", optional=True)),
        outputs=(OperatorPort("out"),),
        modes=("batch",),
    )
    node = Node(
        id=NodeId("node"),
        operator=contract.ref,
        inputs=(Port("extra", "stream"), Port("extra", "stream")),
        outputs=(Port("wrong", "stream"),),
    )
    violations = validate_operator_node(node, OperatorCatalog((contract,)))
    codes = [item.code for item in violations]
    assert codes.count("RONIN-OP-005") == 2
    assert codes.count("RONIN-OP-006") == 2
    assert codes.count("RONIN-OP-007") == 1


def test_node_validation_accepts_all_parameter_kinds_and_extra_policy() -> None:
    parameters = (
        OperatorParameter("any", "any"),
        OperatorParameter("array", "array"),
        OperatorParameter("boolean", "boolean"),
        OperatorParameter("expression", "expression"),
        OperatorParameter("integer", "integer"),
        OperatorParameter("number", "number"),
        OperatorParameter("object", "object"),
        OperatorParameter("string", "string"),
    )
    contract = OperatorContract(
        OperatorRef("types"),
        "Types",
        "test",
        parameters=parameters,
        allow_extra_parameters=True,
    )
    node = _node(
        contract.ref,
        params={
            "any": None,
            "array": ["x"],
            "boolean": True,
            "expression": "x > 1",
            "integer": 1,
            "number": 1.5,
            "object": {"x": 1},
            "string": "value",
            "extra": "allowed",
        },
    )
    assert validate_operator_node(node, OperatorCatalog((contract,))) == ()
    assert operator_parameter_value(node, "array") == ["x"]
    assert operator_parameter_value(node, "missing") is None


def test_node_validation_distinguishes_boolean_from_integer_and_number() -> None:
    contract = OperatorContract(
        OperatorRef("numbers"),
        "Numbers",
        "test",
        parameters=(
            OperatorParameter("integer", "integer"),
            OperatorParameter("number", "number"),
        ),
    )
    node = _node(contract.ref, params={"integer": True, "number": False})
    violations = validate_operator_node(node, OperatorCatalog((contract,)))
    assert [item.path for item in violations] == ["params.integer", "params.number"]
