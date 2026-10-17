from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import artifact_identity
from tools.artifact_identity import SCHEMA, build_manifest


def test_artifact_manifest_is_candidate_bound_and_hashed(tmp_path: Path) -> None:
    wheel = tmp_path / "ronin.whl"
    sdist = tmp_path / "ronin.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    manifest = build_manifest([sdist, wheel], commit="abc123")

    assert manifest["schema"] == SCHEMA
    assert manifest["commit"] == "abc123"
    assert [item["kind"] for item in manifest["artifacts"]] == ["sdist", "wheel"]
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])


def test_artifact_manifest_rejects_missing_or_empty_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_manifest([], commit="abc123")
    with pytest.raises(FileNotFoundError):
        build_manifest([tmp_path / "missing.whl"], commit="abc123")


def test_artifact_manifest_rejects_blank_commit_and_duplicate_names(tmp_path: Path) -> None:
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"wheel")
    with pytest.raises(ValueError, match="commit must be non-empty"):
        build_manifest([artifact], commit=" ")
    first = tmp_path / "one" / "same.whl"
    second = tmp_path / "two" / "same.whl"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    with pytest.raises(ValueError, match="names must be unique"):
        build_manifest([first, second], commit="abc123")


def test_artifact_manifest_classifies_json_text_and_other_files(tmp_path: Path) -> None:
    files = [tmp_path / "a.json", tmp_path / "b.txt", tmp_path / "c.bin"]
    for path in files:
        path.write_bytes(path.name.encode())
    manifest = build_manifest(files, commit="abc123")
    assert [item["kind"] for item in manifest["artifacts"]] == ["evidence", "evidence", "other"]


def test_artifact_identity_cli_writes_manifest_and_uses_git_fallback(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"wheel")
    output = tmp_path / "identity.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["artifact_identity", "--commit", "abc123", "--output", str(output), str(artifact)],
    )
    assert artifact_identity.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["commit"] == "abc123"
    assert '"commit": "abc123"' in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["artifact_identity", "--output", str(output), str(artifact)])
    monkeypatch.setattr(artifact_identity, "git_commit", lambda: "fallback-commit")
    assert artifact_identity.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["commit"] == "fallback-commit"


def test_git_commit_calls_fixed_git_revision_command(monkeypatch) -> None:
    monkeypatch.setattr(
        artifact_identity.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout="exact-sha\n"),
    )
    assert artifact_identity.git_commit() == "exact-sha"

    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(artifact_identity.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        artifact_identity.git_commit()
