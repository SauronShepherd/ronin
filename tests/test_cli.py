from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_cli import main


def test_doctor_reports_required_local_tools(monkeypatch, capsys) -> None:
    monkeypatch.setattr("studio_cli.shutil.which", lambda name: f"/usr/bin/{name}")

    assert main(["doctor"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "python>=3.11: ok" in output.out
    assert "git: ok (/usr/bin/git)" in output.out
    assert "docker: ok (/usr/bin/docker)" in output.out
    assert "doctor: all checks passed" in output.out


def test_doctor_fails_closed_when_required_tool_is_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "studio_cli.shutil.which",
        lambda name: None if name == "git" else f"/usr/bin/{name}",
    )

    assert main(["doctor"]) == 2
    output = capsys.readouterr()
    assert "git: fail (not found)" in output.out
    assert "docker: ok (/usr/bin/docker)" in output.out
    assert output.err == "error: doctor required all checks failed\n"


def test_doctor_core_succeeds_without_docker_but_reports_verdict(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "studio_cli.shutil.which",
        lambda name: None if name == "docker" else f"/usr/bin/{name}",
    )

    assert main(["doctor", "--require=core"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert "python>=3.11: ok" in output.out
    assert "git: ok (/usr/bin/git)" in output.out
    assert "docker: fail (not found)" in output.out
    assert "doctor: required core checks passed" in output.out


def test_doctor_all_still_requires_docker(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "studio_cli.shutil.which",
        lambda name: None if name == "docker" else f"/usr/bin/{name}",
    )

    assert main(["doctor", "--require=all"]) == 2
    output = capsys.readouterr()
    assert "docker: fail (not found)" in output.out
    assert output.err == "error: doctor required all checks failed\n"


def test_validate_and_plan_reuse_canonical_demo_contracts(capsys) -> None:
    assert main(["validate", "examples/demo"]) == 0
    validate_output = capsys.readouterr()
    assert "notebooks: 1" in validate_output.out
    assert "validate: ok" in validate_output.out

    assert main(["plan", "examples/demo", "-t", "notebooks/etl"]) == 0
    plan_output = capsys.readouterr()
    assert "target: notebooks/etl.ronin.json" in plan_output.out
    assert "1. intro" in plan_output.out
    assert "2. extract-customers" in plan_output.out
    assert "3. extract-orders" in plan_output.out
    assert "4. join-and-aggregate" in plan_output.out
    assert "5. quality-check" in plan_output.out
    assert "6. publish" in plan_output.out
    assert "0: intro, extract-customers, extract-orders" in plan_output.out
    assert "1: join-and-aggregate" in plan_output.out
    assert "2: quality-check" in plan_output.out
    assert "3: publish" in plan_output.out


@pytest.mark.parametrize("target", ["../outside", "/outside", " missing "])
def test_plan_rejects_unsafe_or_malformed_targets(target: str, capsys) -> None:
    assert main(["plan", "examples/demo", "-t", target]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("error: ")


def test_validate_rejects_invalid_notebook_dependencies(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    notebooks = project / "notebooks"
    ronin_dir = project / ".ronin"
    notebooks.mkdir(parents=True)
    ronin_dir.mkdir()

    source_manifest = Path("examples/demo/.ronin/project.json").read_text(encoding="utf-8")
    (ronin_dir / "project.json").write_text(source_manifest, encoding="utf-8")
    source_notebook = json.loads(
        Path("examples/demo/notebooks/etl.ronin.json").read_text(encoding="utf-8")
    )
    source_notebook["cells"][1]["dependencies"] = ["missing-cell"]
    (notebooks / "broken.ronin.json").write_text(
        json.dumps(source_notebook),
        encoding="utf-8",
    )

    assert main(["validate", str(project)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "invalid notebook dependencies" in output.err


def test_validate_rejects_missing_project(capsys) -> None:
    assert main(["validate", "does-not-exist"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: project does not exist: does-not-exist\n"
