from __future__ import annotations

import pytest
from studio_core import (
    Node,
    OperatorCatalog,
    OperatorContract,
    OperatorParameter,
    OperatorPort,
    OperatorRef,
    Port,
    ids,
    operators,
    ownership,
    projects,
    sensitivity,
    versions,
    workspaces,
)


@pytest.mark.parametrize(
    "validator",
    [
        operators._require_text,
        projects._require_text,
        workspaces._require_text,
    ],
)
@pytest.mark.parametrize("value", [123, "value\x00tail"])
def test_domain_text_validators_reject_non_text_and_nul(validator, value: object) -> None:
    with pytest.raises(ValueError, match="."):
        validator(value, "field")  # type: ignore[arg-type]


def test_operator_canonical_texts_reject_non_text_values() -> None:
    with pytest.raises(ValueError, match=r"^capability must be non-empty$"):
        operators._canonical_texts((123,), "capability")  # type: ignore[arg-type]


def test_sensitivity_labels_reject_non_text_values() -> None:
    with pytest.raises(ValueError, match=r"^explicit labels must contain non-empty labels$"):
        sensitivity._labels((123,), "explicit labels")  # type: ignore[arg-type]


def test_ownership_refs_reject_non_text_values() -> None:
    with pytest.raises(
        ValueError, match=r"^steward_refs must contain unique non-empty references$"
    ):
        ownership._refs((123,), "steward_refs")  # type: ignore[arg-type]


def test_release_parser_is_total_for_non_text_values() -> None:
    assert versions.parse_comparable_release(123) is None  # type: ignore[arg-type]
    assert versions.compare_releases(123, "1.0") is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "constraint",
    [">=3.11", "<=4", ">3", "<5", "==stable", "!=vendor", "opaque"],
)
def test_capability_constraints_accept_each_supported_comparison_form(constraint: str) -> None:
    assert projects.CapabilityRequirement("runtime", constraint).constraint == constraint


@pytest.mark.parametrize("constraint", [",", ">=", "<", ">=four", "<=vendor"])
def test_capability_constraints_reject_empty_or_non_version_ordered_terms(constraint: str) -> None:
    with pytest.raises(ValueError, match="."):
        projects.CapabilityRequirement("runtime", constraint)


def test_release_comparison_orders_prereleases_and_normalizes_release_width() -> None:
    assert versions.compare_releases("1.0dev", "1.0a1") == -1
    assert versions.compare_releases("1.0a1", "1.0beta1") == -1
    assert versions.compare_releases("1.0beta1", "1.0rc1") == -1
    assert versions.compare_releases("1.0rc1", "1.0") == -1
    assert versions.compare_releases("1.2", "1.2.0") == 0
    assert versions.compare_releases("1.2+vendor", "1.2") == 0


def test_operator_validation_distinguishes_optional_ports_and_parameter_kinds() -> None:
    ref = OperatorRef("matrix")
    contract = OperatorContract(
        ref,
        "Matrix",
        "test",
        inputs=(OperatorPort("required"), OperatorPort("optional", optional=True)),
        outputs=(OperatorPort("out"),),
        parameters=(
            OperatorParameter("flag", "boolean"),
            OperatorParameter("count", "integer"),
            OperatorParameter("ratio", "number"),
            OperatorParameter("items", "array"),
            OperatorParameter("record", "object"),
        ),
    )
    node = Node.create(
        operator=ref,
        instance_key="matrix",
        params={"flag": True, "count": 2, "ratio": 2.5, "items": ["x"], "record": {"x": 1}},
        inputs=(Port("required"),),
        outputs=(Port("out"),),
    )
    assert operators.validate_operator_node(node, OperatorCatalog((contract,))) == ()


def test_operator_validation_rejects_bool_as_integer_or_number_and_reports_missing_port() -> None:
    ref = OperatorRef("strict")
    contract = OperatorContract(
        ref,
        "Strict",
        "test",
        inputs=(OperatorPort("required"),),
        parameters=(OperatorParameter("count", "integer"), OperatorParameter("ratio", "number")),
    )
    node = Node.create(
        operator=ref,
        instance_key="strict",
        params={"count": True, "ratio": False},
    )
    violations = operators.validate_operator_node(node, OperatorCatalog((contract,)))
    assert {violation.path for violation in violations} == {
        "params.count",
        "params.ratio",
        "inputs.required",
    }


@pytest.mark.parametrize("value", [123, "value\x00tail"])
def test_instance_anchor_rejects_noncanonical_references(value: object) -> None:
    with pytest.raises(ValueError, match="."):
        ids.InstanceAnchor("authoring", value)  # type: ignore[arg-type]
