from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from studio_vcs import GitCaptureError, GitRevision, capture_revision
from studio_vcs.git import _normalized_untracked_mode


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        (shutil.which("git") or "git", "-C", str(path), *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Ronin Test")
    _git(root, "config", "user.email", "ronin@example.invalid")
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-qm", "initial")
    return root


def test_clean_revision_matches_head(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    captured = capture_revision(root / "tracked.txt")
    assert captured.commit == _git(root, "rev-parse", "HEAD")
    assert captured.dirty_patch_sha256 is None


def test_tracked_and_untracked_dirty_digest_is_deterministic(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "tracked.txt").write_text("two\n", encoding="utf-8")
    (root / "z.txt").write_text("z\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    first = capture_revision(root)
    second = capture_revision(root)
    assert first == second
    assert first.dirty_patch_sha256 is not None
    assert len(first.dirty_patch_sha256) == 64


def test_untracked_content_changes_dirty_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    untracked = root / "new.txt"
    untracked.write_text("first", encoding="utf-8")
    first = capture_revision(root)
    untracked.write_text("second", encoding="utf-8")
    second = capture_revision(root)
    assert first.commit == second.commit
    assert first.dirty_patch_sha256 != second.dirty_patch_sha256


@pytest.mark.skipif(os.name != "posix", reason="executable mode is POSIX-specific")
def test_untracked_executable_mode_changes_dirty_identity(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    untracked = root / "tool.sh"
    untracked.write_text("#!/bin/sh\n", encoding="utf-8")
    regular = capture_revision(root)
    untracked.chmod(untracked.stat().st_mode | stat.S_IXUSR)
    executable = capture_revision(root)
    assert regular.dirty_patch_sha256 != executable.dirty_patch_sha256


def test_untracked_mode_normalization_uses_git_file_modes(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_text("x", encoding="utf-8")
    assert _normalized_untracked_mode(path.stat()) == b"100644"
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    expected = b"100755" if os.name == "posix" else b"100644"
    assert _normalized_untracked_mode(path.stat()) == expected


def test_capture_rejects_non_repository(tmp_path: Path) -> None:
    with pytest.raises(GitCaptureError):
        capture_revision(tmp_path)


def test_revision_value_contract_rejects_invalid_hex() -> None:
    with pytest.raises(ValueError, match="commit"):
        GitRevision("xyz")
    with pytest.raises(ValueError, match="dirty"):
        GitRevision("a" * 40, "z" * 64)
