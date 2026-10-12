from __future__ import annotations

import pytest
from studio_core import ids, operators, ownership, projects, sensitivity, versions, workspaces


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


@pytest.mark.parametrize("value", [123, "value\x00tail"])
def test_instance_anchor_rejects_noncanonical_references(value: object) -> None:
    with pytest.raises(ValueError, match="."):
        ids.InstanceAnchor("authoring", value)  # type: ignore[arg-type]
