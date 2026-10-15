from __future__ import annotations

import pytest
from studio_core import projects, workspaces


@pytest.mark.parametrize("validator", [projects._require_text, workspaces._require_text])
@pytest.mark.parametrize("value", ["", " ", " value", "value "])
def test_project_workspace_text_validators_reject_blank_and_untrimmed(
    validator, value: str
) -> None:
    with pytest.raises(ValueError, match=".") as error:
        validator(value, "identity")
    assert str(error.value) == "identity must be non-empty and trimmed"


@pytest.mark.parametrize("validator", [projects._require_text, workspaces._require_text])
@pytest.mark.parametrize("value", ["line\nfeed", "carriage\rreturn"])
def test_project_workspace_text_validators_reject_each_line_break(validator, value: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        validator(value, "identity")
    assert str(error.value) == "identity must not contain line breaks"


def test_capability_constraint_checks_each_term_after_unknown_decorations() -> None:
    projects._validate_constraint("vendor-decoration, >=3.11")
    with pytest.raises(ValueError, match=".") as error:
        projects._validate_constraint("vendor-decoration, >=")
    assert str(error.value) == "capability constraint is missing a value"


@pytest.mark.parametrize(
    ("constraint", "message"),
    [
        ("vendor-decoration,, >=3.11", "capability constraint contains an empty term"),
        (">=", "capability constraint is missing a value"),
        (">=python", "ordered capability constraint requires a version-like value"),
    ],
)
def test_capability_constraint_diagnostics_are_exact(constraint: str, message: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        projects._validate_constraint(constraint)
    assert str(error.value) == message
