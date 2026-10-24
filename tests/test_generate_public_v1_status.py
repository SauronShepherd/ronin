from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import tools.generate_public_v1_status as status


def test_synchronize_updates_machine_and_human_ledgers(tmp_path: Path, monkeypatch) -> None:
    machine = tmp_path / "status.json"
    markdown = tmp_path / "status.md"
    machine.write_text(
        json.dumps({"schema_version": 1, "observed_main_sha": "a" * 40}), encoding="utf-8"
    )
    markdown.write_text(
        "**Observed source head:** `" + "a" * 40 + "` (2026-09-17).\n", encoding="utf-8"
    )
    monkeypatch.setattr(status, "MACHINE", machine)
    monkeypatch.setattr(status, "MARKDOWN", markdown)

    status.synchronize("b" * 40, "2026-09-18T12:00:00Z")
    assert json.loads(machine.read_text(encoding="utf-8"))["observed_main_sha"] == "b" * 40
    assert "`" + "b" * 40 + "` (2026-09-18)." in markdown.read_text(encoding="utf-8")


def test_synchronize_rejects_invalid_sha(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(status, "MACHINE", tmp_path / "status.json")
    monkeypatch.setattr(status, "MARKDOWN", tmp_path / "status.md")
    with pytest.raises(ValueError, match="40-character"):
        status.synchronize("not-a-sha", "2026-09-18T12:00:00Z")


def test_check_uses_explicit_base_reference(monkeypatch) -> None:
    observed = "a" * 40
    base = "b" * 40
    commands: list[list[str]] = []
    monkeypatch.setattr(status, "_read_observed", lambda: (observed, observed))

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[1] == "rev-list":
            return subprocess.CompletedProcess(command, 0, "0\n", "")
        if command[1] == "merge-base":
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected git command: {command}")

    monkeypatch.setattr(status.subprocess, "run", run)
    status.check(reference_sha=base)

    assert commands == [
        ["git", "rev-list", "--count", "--no-merges", f"{observed}..{base}"],
        ["git", "merge-base", "--is-ancestor", observed, base],
    ]


def test_check_rejects_invalid_explicit_reference(monkeypatch) -> None:
    monkeypatch.setattr(status, "_read_observed", lambda: ("a" * 40, "a" * 40))

    with pytest.raises(SystemExit, match="invalid status reference SHA"):
        status.check(reference_sha="not-a-sha")
