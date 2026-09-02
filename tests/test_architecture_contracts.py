from __future__ import annotations

import tempfile
from pathlib import Path

from tools.architecture_gate import inspect_file, inspect_roots
from tools.gates_negative import run_negative_cases


def _fixture(directory: str, package: str, source: str) -> Path:
    path = Path(directory) / "python" / package / "fixture.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_current_project_respects_architecture_contracts() -> None:
    assert inspect_roots([Path("python")]) == []


def test_gate_rejects_forbidden_io() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(directory, "studio_core", "import sqlite3\nopen('state.txt')\n")
        violations = inspect_file(path)

    assert {violation.rule for violation in violations} == {"IO001", "IO002"}


def test_gate_rejects_environment_access_through_import_alias() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(
            directory,
            "studio_core",
            "import os as operating_system\nTOKEN = operating_system.environ['TOKEN']\n",
        )
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["IO003"]


def test_gate_rejects_environment_access_through_from_import() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(
            directory,
            "studio_core",
            "from os import environ\nTOKEN = environ['TOKEN']\n",
        )
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["IO003"]


def test_gate_rejects_forbidden_project_dependency() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(directory, "studio_core", "from studio_server import app\n")
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["DEP001"]


def test_gate_allows_declared_project_dependency() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(directory, "studio_notebook", "from studio_core import diagnostics\n")
        violations = inspect_file(path)

    assert violations == []


def test_gate_rejects_undeclared_project_package() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(directory, "studio_future", "VALUE = 1\n")
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["DEP000"]


def test_negative_gate_harness_detects_all_fixtures() -> None:
    assert run_negative_cases() == []
