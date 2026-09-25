from pathlib import Path

import pytest

from tools.public_import_smoke import declared_packages, import_packages


def test_declared_packages_are_unique_and_ordered(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.mypy]\npackages = ["alpha", "beta"]\n', encoding="utf-8")

    assert declared_packages(pyproject) == ("alpha", "beta")


def test_import_smoke_reports_each_failure_without_stopping() -> None:
    result = import_packages(("json", "module_that_does_not_exist_for_smoke"))

    assert result["imported"] == ["json"]
    assert "module_that_does_not_exist_for_smoke" in result["failures"]


def test_declared_packages_reject_duplicates(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.mypy]\npackages = ["alpha", "alpha"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        declared_packages(pyproject)
