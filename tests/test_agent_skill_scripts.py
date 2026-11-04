from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = write_bytecode
    return module


@pytest.fixture
def core_preflight() -> ModuleType:
    return _load_script(
        "ronin_core_preflight",
        ROOT / "agent-skills" / "ronin-core" / "scripts" / "preflight.py",
    )


@pytest.fixture
def engineering_preflight() -> ModuleType:
    return _load_script(
        "ronin_data_engineering_preflight",
        ROOT / "agent-skills" / "ronin-data-engineering" / "scripts" / "preflight.py",
    )


@pytest.fixture
def ml_openapi_verifier() -> ModuleType:
    return _load_script(
        "ronin_ml_openapi_verifier",
        ROOT / "agent-skills" / "ronin-machine-learning" / "scripts" / "verify_openapi.py",
    )


def _completed(
    command: list[str], output: str, returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout=output, stderr="")


def test_core_preflight_reports_all_required_commands(
    core_preflight: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(core_preflight.shutil, "which", lambda _value: "ronin")
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])
    monkeypatch.setattr(
        core_preflight.subprocess,
        "run",
        lambda command, **_kwargs: _completed(command, " ".join(sorted(core_preflight.REQUIRED))),
    )

    assert core_preflight.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["missing"] == []


def test_core_preflight_returns_structured_missing_executable(
    core_preflight: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(core_preflight.shutil, "which", lambda _value: None)
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])

    assert core_preflight.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "ronin_not_found"
    assert result["missing"] == sorted(core_preflight.REQUIRED)


def test_core_preflight_reports_timeout_without_traceback(
    core_preflight: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(core_preflight.shutil, "which", lambda _value: "ronin")
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])

    def timeout(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired("ronin", 10)

    monkeypatch.setattr(core_preflight.subprocess, "run", timeout)

    assert core_preflight.main() == 2
    assert json.loads(capsys.readouterr().out)["error"] == "ronin_check_failed"


def test_data_engineering_preflight_checks_top_level_and_connector_commands(
    engineering_preflight: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(engineering_preflight.shutil, "which", lambda _value: "ronin")
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        expected = (
            engineering_preflight.TOP if command[1:] == ["--help"] else engineering_preflight.SUB
        )
        return _completed(command, " ".join(sorted(expected)))

    monkeypatch.setattr(engineering_preflight.subprocess, "run", run)

    assert engineering_preflight.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["missing_top"] == []
    assert result["missing_connectors"] == []


def test_data_engineering_preflight_reports_missing_connector_surface(
    engineering_preflight: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(engineering_preflight.shutil, "which", lambda _value: "ronin")
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        output = " ".join(sorted(engineering_preflight.TOP))
        if command[1:] == ["connectors", "--help"]:
            output = "capabilities discover"
        return _completed(command, output)

    monkeypatch.setattr(engineering_preflight.subprocess, "run", run)

    assert engineering_preflight.main() == 3
    result = json.loads(capsys.readouterr().out)
    assert result["missing_connectors"] == ["checkpoint-health", "plan", "preview"]


def test_ml_openapi_verifier_counts_only_http_operations(
    ml_openapi_verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(
        json.dumps(
            {
                "paths": {
                    "/v1/ml-studio/models": {"get": {}, "post": {}, "parameters": []},
                    "/v1/ml-studio/experiments": {"delete": {}},
                    "/v1/projects": {"get": {}},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_openapi.py", "--openapi", str(spec_path), "--json"],
    )

    assert ml_openapi_verifier.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ml_paths"] == 2
    assert result["ml_operations"] == 3


@pytest.mark.parametrize(
    ("contents", "expected_error"),
    [("{invalid", "invalid_openapi"), ('{"openapi":"3.1.0"}', "missing_paths")],
)
def test_ml_openapi_verifier_reports_invalid_documents(
    ml_openapi_verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    contents: str,
    expected_error: str,
) -> None:
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_openapi.py", "--openapi", str(spec_path), "--json"],
    )

    assert ml_openapi_verifier.main() == 2
    assert json.loads(capsys.readouterr().out)["error"] == expected_error


def test_ml_openapi_verifier_rejects_non_object_ml_path_item(
    ml_openapi_verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps({"paths": {"/v1/ml-studio/models": []}}), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_openapi.py", "--openapi", str(spec_path), "--json"],
    )

    assert ml_openapi_verifier.main() == 2
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_path_item"
