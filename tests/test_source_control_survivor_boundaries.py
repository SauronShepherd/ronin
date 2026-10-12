from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import source_control


@pytest.mark.parametrize("value", ["line\nfeed", "carriage\rreturn", " ", ""])
def test_source_text_validator_rejects_each_noncanonical_form(value: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        source_control._text(value, "source field")
    assert str(error.value) == "source field must be non-empty and single-line"


def test_source_text_validator_rejects_non_string_values_with_stable_message() -> None:
    with pytest.raises(ValueError, match=".") as error:
        source_control._text(123, "source field")  # type: ignore[arg-type]
    assert str(error.value) == "source field must be non-empty and single-line"


def test_safe_checkout_path_normalizes_empty_dot_and_nested_components(tmp_path: Path) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    assert source_control.safe_checkout_path(root) == root
    assert source_control.safe_checkout_path(root, "./nested/./leaf") == root / "nested" / "leaf"
    assert source_control.safe_checkout_path(root, "nested/leaf") == root / "nested" / "leaf"


def test_safe_checkout_path_reports_exact_escape_diagnostic(tmp_path: Path) -> None:
    root = tmp_path / "worktree"
    root.mkdir()
    with pytest.raises(ValueError, match=".") as error:
        source_control.safe_checkout_path(root, "../outside")
    assert str(error.value) == "checkout subdirectory escapes the worktree"
