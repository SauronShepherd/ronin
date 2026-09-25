from pathlib import Path

import pytest

from studio_core import SourceRepository
from studio_execution import GitSourceAdapter, GitSourceError


def test_git_checkout_rejects_dirty_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    adapter = GitSourceAdapter()
    monkeypatch.setattr(adapter, "is_dirty", lambda _path: True)
    with pytest.raises(GitSourceError, match="dirty"):
        adapter.checkout_detached(root, SourceRepository("file:///repo", "main"))


def test_source_repository_exposes_credential_free_uri_validation() -> None:
    assert SourceRepository.validate_uri("https://git.example/repo.git") == (
        "https://git.example/repo.git"
    )
    with pytest.raises(ValueError, match="credential"):
        SourceRepository.validate_uri("https://user:secret@git.example/repo.git")


def test_git_checkout_is_detached_and_returns_resolved_subdirectory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    calls: list[tuple[str, ...]] = []
    adapter = GitSourceAdapter()
    monkeypatch.setattr(adapter, "is_dirty", lambda _path: False)

    def run(_path: Path, *args: str) -> str:
        calls.append(args)
        return "deadbeef" if args[0] == "rev-parse" else ""

    monkeypatch.setattr(adapter, "_run", run)
    result = adapter.checkout_detached(
        root,
        SourceRepository("file:///repo", "main"),
        subdirectory="src",
    )
    assert result.commit == "deadbeef"
    assert result.worktree == root / "src"
    assert ("checkout", "--detach", "--", "deadbeef") in calls


def test_git_update_fetches_before_detached_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    adapter = GitSourceAdapter()
    monkeypatch.setattr(adapter, "is_dirty", lambda _path: False)
    calls: list[tuple[str, ...]] = []

    def run(_path: Path, *args: str) -> str:
        calls.append(args)
        return "updated-commit" if args[0] == "rev-parse" else ""

    monkeypatch.setattr(adapter, "_run", run)
    result = adapter.update(root, SourceRepository("file:///repo", "main"))

    assert result.commit == "updated-commit"
    assert calls[0] == ("fetch", "--no-tags", "--prune", "file:///repo", "main")
