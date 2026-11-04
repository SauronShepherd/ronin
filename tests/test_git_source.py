import subprocess
from pathlib import Path

import pytest
from studio_core import SourceRepository
from studio_execution import GitSourceAdapter, GitSourceError


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(  # noqa: S603
        ("git", "-C", str(path), *args),  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Ronin Test")
    _git(path, "config", "user.email", "ronin@example.invalid")
    (path / "src").mkdir()
    (path / "src" / "version.txt").write_text("first\n", encoding="utf-8")
    _git(path, "add", "src/version.txt")
    _git(path, "commit", "-qm", "first")
    return path


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
        return "a" * 40 if args[0] == "rev-parse" else ""

    monkeypatch.setattr(adapter, "_run", run)
    result = adapter.checkout_detached(
        root,
        SourceRepository("file:///repo", "main"),
        subdirectory="src",
    )
    assert result.commit == "a" * 40
    assert result.worktree == root / "src"
    assert ("checkout", "--detach", "a" * 40) in calls


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
        return "b" * 40 if args[0] == "rev-parse" else ""

    monkeypatch.setattr(adapter, "_run", run)
    result = adapter.update(root, SourceRepository("file:///repo", "main"))

    assert result.commit == "b" * 40
    assert calls[0] == ("fetch", "--no-tags", "--prune", "file:///repo", "main")
    assert calls[1] == (
        "rev-parse",
        "--verify",
        "--end-of-options",
        "FETCH_HEAD^{commit}",
    )


def test_git_checkout_uses_real_detached_commit_and_exact_subdirectory(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    first = _git(root, "rev-parse", "HEAD")
    (root / "src" / "version.txt").write_text("second\n", encoding="utf-8")
    _git(root, "add", "src/version.txt")
    _git(root, "commit", "-qm", "second")

    result = GitSourceAdapter().checkout_detached(
        root,
        SourceRepository("https://git.example.invalid/repo.git", first),
        subdirectory="src",
    )

    assert result.commit == first
    assert _git(root, "rev-parse", "HEAD") == first
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert result.worktree == (root / "src").resolve()
    assert (result.worktree / "version.txt").read_text(encoding="utf-8") == "first\n"


def test_git_update_checks_out_the_fetched_remote_commit(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _git(root, "branch", "-M", "main")
    first = _git(root, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")

    (root / "src" / "version.txt").write_text("remote second\n", encoding="utf-8")
    _git(root, "add", "src/version.txt")
    _git(root, "commit", "-qm", "remote second")
    second = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "reset", "--hard", first)

    result = GitSourceAdapter().update(
        root,
        SourceRepository(remote.as_uri(), "refs/heads/main"),
    )

    assert result.commit == second
    assert _git(root, "rev-parse", "HEAD") == second
    assert (root / "src" / "version.txt").read_text(encoding="utf-8") == "remote second\n"
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"


def test_git_fast_forward_advances_only_when_current_commit_is_ancestor(tmp_path: Path) -> None:
    root = _repository(tmp_path / "checkout")
    _git(root, "branch", "-M", "main")
    first = _git(root, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")
    (root / "src" / "version.txt").write_text("second\n", encoding="utf-8")
    _git(root, "add", "src/version.txt")
    _git(root, "commit", "-qm", "second")
    second = _git(root, "rev-parse", "HEAD")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "reset", "--hard", first)
    _git(root, "branch", "--set-upstream-to=origin/main", "main")

    result = GitSourceAdapter().fast_forward(
        root,
        SourceRepository(remote.as_uri(), "refs/heads/main"),
        subdirectory="src",
    )

    assert result.commit == second
    assert result.worktree == (root / "src").resolve()
    assert _git(root, "rev-parse", "HEAD") == second
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_git_fast_forward_is_noop_when_already_at_source(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _git(root, "branch", "-M", "main")
    commit = _git(root, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")
    result = GitSourceAdapter().fast_forward(
        root,
        SourceRepository(remote.as_uri(), "refs/heads/main"),
    )
    assert result.commit == commit
    assert _git(root, "rev-parse", "HEAD") == commit


def test_git_fast_forward_never_rewinds_local_branch_ahead_of_source(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    _git(root, "branch", "-M", "main")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")
    source_commit = _git(root, "rev-parse", "HEAD")
    (root / "src" / "version.txt").write_text("local ahead\n", encoding="utf-8")
    _git(root, "add", "src/version.txt")
    _git(root, "commit", "-qm", "local ahead")
    local_commit = _git(root, "rev-parse", "HEAD")

    result = GitSourceAdapter().fast_forward(
        root,
        SourceRepository(remote.as_uri(), "refs/heads/main"),
    )

    assert source_commit != local_commit
    assert result.commit == local_commit
    assert _git(root, "rev-parse", "HEAD") == local_commit


def test_git_fetch_revision_does_not_change_worktree_head(tmp_path: Path) -> None:
    root = _repository(tmp_path / "checkout")
    _git(root, "branch", "-M", "main")
    commit = _git(root, "rev-parse", "HEAD")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")

    fetched = GitSourceAdapter().fetch_revision(
        root,
        SourceRepository(remote.as_uri(), "refs/heads/main"),
    )

    assert fetched == commit
    assert _git(root, "rev-parse", "HEAD") == commit


def test_git_fast_forward_rejects_dirty_and_detached_worktrees(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    adapter = GitSourceAdapter()

    (root / "src" / "version.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(GitSourceError, match="dirty"):
        adapter.fast_forward(root, SourceRepository(remote.as_uri(), "main"))
    _git(root, "checkout", "--", ".")
    _git(root, "checkout", "--detach", "HEAD")
    with pytest.raises(GitSourceError, match="detached"):
        adapter.fast_forward(root, SourceRepository(remote.as_uri(), "main"))


def test_git_fast_forward_rejects_divergent_history(tmp_path: Path) -> None:
    root = _repository(tmp_path / "checkout")
    _git(root, "branch", "-M", "main")
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "origin", "main")
    _git(root, "checkout", "-b", "other")
    (root / "src" / "version.txt").write_text("divergent local\n", encoding="utf-8")
    _git(root, "add", "src/version.txt")
    _git(root, "commit", "-qm", "divergent local")
    _git(root, "checkout", "main")
    (root / "src" / "version.txt").write_text("remote\n", encoding="utf-8")
    _git(root, "add", "src/version.txt")
    _git(root, "commit", "-qm", "remote commit")
    _git(root, "push", "-q", "origin", "main")
    _git(root, "checkout", "other")

    with pytest.raises(GitSourceError, match="diverged"):
        GitSourceAdapter().fast_forward(
            root,
            SourceRepository(remote.as_uri(), "refs/heads/main"),
        )


def test_git_sync_rejects_unsafe_subdirectory_before_changing_head(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    commit = _git(root, "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="escapes"):
        GitSourceAdapter().fast_forward(
            root,
            SourceRepository("file:///unreachable/repo", "main"),
            subdirectory="../outside",
        )
    assert _git(root, "rev-parse", "HEAD") == commit


def test_git_checkout_rejects_symlink_subdirectory_before_checkout(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    first = _git(root, "rev-parse", "HEAD")
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("symlink creation requires Windows developer privileges")
        raise

    with pytest.raises(ValueError, match="symlink"):
        GitSourceAdapter().checkout_detached(
            root,
            SourceRepository("https://git.example.invalid/repo.git", first),
            subdirectory="linked",
        )
    assert _git(root, "rev-parse", "HEAD") == first


def test_git_adapter_ignores_ambient_repository_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _repository(tmp_path / "target")
    other = _repository(tmp_path / "other")
    (other / "src" / "version.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(other))

    assert GitSourceAdapter().is_dirty(target) is False
