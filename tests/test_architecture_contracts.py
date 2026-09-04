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


def test_gate_rejects_real_io_network_process_and_unsafe_deserialization_imports() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = (
            "from pathlib import Path\n"
            "import io\n"
            "import socket\n"
            "import pickle\n"
            "from urllib import request\n"
        )
        path = _fixture(directory, "studio_core", source)
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["IO001"] * 5


def test_gate_rejects_os_side_effects_and_getenv() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(
            directory,
            "studio_core",
            "import os\nos.getenv('TOKEN')\nos.system('echo unsafe')\n",
        )
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["IO003", "IO001"]


def test_gate_rejects_nondeterministic_sources_separately() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = (
            "import time\n"
            "import random\n"
            "import uuid\n"
            "import os\n"
            "VALUE = time.time() + random.random()\n"
            "TOKEN = os.urandom(4)\n"
            "ID = uuid.uuid4()\n"
        )
        path = _fixture(directory, "studio_core", source)
        violations = inspect_file(path)

    assert all(violation.rule == "IO004" for violation in violations)
    assert len(violations) >= 4


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


def test_gate_allows_explicit_pure_standard_library_imports() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(
            directory,
            "studio_core",
            "import json\nimport hashlib\nfrom urllib.parse import urlsplit\n",
        )
        violations = inspect_file(path)

    assert violations == []


def test_gate_rejects_undeclared_project_package() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(directory, "studio_future", "VALUE = 1\n")
        violations = inspect_file(path)

    assert [violation.rule for violation in violations] == ["DEP000"]


def test_source_package_is_relative_to_gate_root_not_checkout_parent_name() -> None:
    with tempfile.TemporaryDirectory(prefix="studio_workspace_") as directory:
        path = _fixture(directory, "studio_core", "VALUE = 1\n")
        root = Path(directory) / "python"
        violations = inspect_file(path, root=root)

    assert violations == []


def test_gate_reports_syntax_error_as_violation_instead_of_crashing() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _fixture(directory, "studio_core", "def broken(:\n")
        violations = inspect_file(path)

    assert len(violations) == 1
    assert violations[0].rule == "PARSE001"
    assert "invalid Python syntax" in violations[0].detail


def test_negative_gate_harness_detects_all_fixtures() -> None:
    assert run_negative_cases() == []
