from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from studio_vcs import GitCaptureError, GitRevision, capture_revision


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603
        ("/usr/bin/git", "-C", str(path), *args),
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


def test_capture_rejects_non_repository(tmp_path: Path) -> None:
    with pytest.raises(GitCaptureError):
        capture_revision(tmp_path)


def test_revision_value_contract_rejects_invalid_hex() -> None:
    with pytest.raises(ValueError, match="commit"):
        GitRevision("xyz")
    with pytest.raises(ValueError, match="dirty"):
        GitRevision("a" * 40, "z" * 64)
