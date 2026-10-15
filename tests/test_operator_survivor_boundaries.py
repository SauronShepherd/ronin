from __future__ import annotations

import pytest
from studio_core import (
    Node,
    OperatorCatalog,
    OperatorContract,
    OperatorParameter,
    OperatorPort,
    OperatorRef,
    OperatorViolation,
    Port,
    operators,
    validate_operator_node,
)


def test_canonical_capability_texts_sort_and_reject_duplicate_or_invalid_values() -> None:
    assert operators._canonical_texts(("z", "a"), "capability") == ("a", "z")

    with pytest.raises(ValueError, match=".") as duplicate_error:
        operators._canonical_texts(("engine.sql", "engine.sql"), "capability")
    assert str(duplicate_error.value) == "capability values must be unique"

    with pytest.raises(ValueError, match=".") as invalid_error:
        operators._canonical_texts(("bad\nvalue",), "capability")
    assert str(invalid_error.value) == "capability must not contain line breaks"


def test_validate_ports_returns_stable_duplicate_unknown_and_missing_diagnostics() -> None:
    actual = (Port("extra"), Port("extra"))
    declared = (OperatorPort("required"), OperatorPort("optional", optional=True))

    violations = operators._validate_ports(actual, declared, "inputs")

    assert violations == [
        OperatorViolation(
            "RONIN-OP-005", "node inputs contain duplicate port: extra", "inputs.extra"
        ),
        OperatorViolation(
            "RONIN-OP-006", "node inputs contain undeclared port: extra", "inputs.extra"
        ),
        OperatorViolation(
            "RONIN-OP-005", "node inputs are missing required port: required", "inputs.required"
        ),
    ]


def test_validate_operator_node_keeps_all_parameter_and_port_contract_fields() -> None:
    ref = OperatorRef("diagnostics.complete")
    contract = OperatorContract(
        ref,
        "Diagnostics",
        "test",
        inputs=(OperatorPort("required"),),
        outputs=(OperatorPort("out"),),
        parameters=(OperatorParameter("required", "string", required=True),),
        modes=("batch",),
    )
    node = Node.create(
        operator=ref,
        instance_key="complete",
        params={"required": 1, "extra": True},
        inputs=(Port("wrong", "stream"), Port("wrong", "stream")),
        outputs=(Port("out", "stream"),),
    )

    assert validate_operator_node(node, OperatorCatalog((contract,))) == (
        OperatorViolation(
            "RONIN-OP-003",
            "operator parameter has incompatible type: required",
            "params.required",
        ),
        OperatorViolation(
            "RONIN-OP-004",
            "operator parameter is not declared by the contract: extra",
            "params.extra",
        ),
        OperatorViolation(
            "RONIN-OP-005",
            "node inputs are missing required port: required",
            "inputs.required",
        ),
        OperatorViolation(
            "RONIN-OP-005",
            "node inputs contain duplicate port: wrong",
            "inputs.wrong",
        ),
        OperatorViolation(
            "RONIN-OP-006",
            "node inputs contain undeclared port: wrong",
            "inputs.wrong",
        ),
        OperatorViolation(
            "RONIN-OP-007",
            "operator does not support stream ports",
            "ports",
        ),
    )


def test_validate_operator_node_keeps_exact_parameter_and_mode_diagnostics() -> None:
    ref = OperatorRef("diagnostics.exact")
    contract = OperatorContract(
        ref,
        "Diagnostics",
        "test",
        inputs=(OperatorPort("input"),),
        parameters=(OperatorParameter("limit", "integer"),),
        modes=("batch",),
    )
    node = Node.create(
        operator=ref,
        instance_key="exact",
        params={"limit": "not-an-integer", "extra": True},
        inputs=(Port("input", "stream"),),
    )

    assert validate_operator_node(node, OperatorCatalog((contract,))) == (
        OperatorViolation(
            "RONIN-OP-003",
            "operator parameter has incompatible type: limit",
            "params.limit",
        ),
        OperatorViolation(
            "RONIN-OP-004",
            "operator parameter is not declared by the contract: extra",
            "params.extra",
        ),
        OperatorViolation(
            "RONIN-OP-007",
            "operator does not support stream ports",
            "ports",
        ),
    )


def test_validate_ports_keeps_each_diagnostic_code_and_path_exact() -> None:
    violations = operators._validate_ports(
        (Port("duplicate"), Port("duplicate"), Port("unknown")),
        (OperatorPort("required"),),
        "outputs",
    )

    assert violations == [
        OperatorViolation(
            "RONIN-OP-005",
            "node outputs contain duplicate port: duplicate",
            "outputs.duplicate",
        ),
        OperatorViolation(
            "RONIN-OP-006",
            "node outputs contain undeclared port: duplicate",
            "outputs.duplicate",
        ),
        OperatorViolation(
            "RONIN-OP-006",
            "node outputs contain undeclared port: unknown",
            "outputs.unknown",
        ),
        OperatorViolation(
            "RONIN-OP-005",
            "node outputs are missing required port: required",
            "outputs.required",
        ),
    ]
