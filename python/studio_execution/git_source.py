"""Bounded Git source operations behind a provider-neutral execution boundary."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from studio_core.source_control import SourceRepository, safe_checkout_path

_COMMIT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class GitSourceError(RuntimeError):
    """Raised when a bounded Git source operation cannot be completed."""


@dataclass(frozen=True, slots=True)
class GitCheckoutResult:
    repository: SourceRepository
    worktree: Path
    commit: str
    dirty_before: bool


class GitSourceAdapter:
    """Run only explicit, non-interactive Git commands against a worktree."""

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Git timeout must be positive")
        self._timeout = timeout_seconds

    def _run(self, worktree: Path, *args: str) -> str:
        try:
            result = subprocess.run(  # noqa: S603
                ("git", "-C", str(worktree), *args),  # noqa: S607
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise GitSourceError(f"git operation failed: {' '.join(args)}") from exc
        return result.stdout.strip()

    def is_dirty(self, worktree: Path) -> bool:
        return bool(self._run(worktree, "status", "--porcelain", "--untracked-files=all"))

    def fetch(self, worktree: Path, repository: SourceRepository) -> str:
        self._run(worktree, "fetch", "--no-tags", "--prune", repository.uri, repository.revision)
        return self._resolve_commit(worktree, "FETCH_HEAD")

    def _resolve_commit(self, worktree: Path, revision: str) -> str:
        commit = self._run(
            worktree,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{revision}^{{commit}}",
        )
        if not _COMMIT_ID.fullmatch(commit):
            raise GitSourceError("git revision did not resolve to an immutable commit id")
        return commit

    def checkout_detached(
        self,
        worktree: Path,
        repository: SourceRepository,
        *,
        subdirectory: str = "",
        allow_dirty: bool = False,
        fetch: bool = False,
    ) -> GitCheckoutResult:
        root = worktree.resolve()
        dirty = self.is_dirty(root)
        if dirty and not allow_dirty:
            raise GitSourceError("refusing checkout in a dirty worktree")
        if fetch:
            commit = self.fetch(root, repository)
        else:
            commit = self._resolve_commit(root, repository.revision)
        # `--` makes the following SHA a pathspec. The revision has already
        # been resolved and validated as a commit id, so pass it as a revision.
        self._run(root, "checkout", "--detach", commit)
        return GitCheckoutResult(repository, safe_checkout_path(root, subdirectory), commit, dirty)

    def update(
        self,
        worktree: Path,
        repository: SourceRepository,
        *,
        subdirectory: str = "",
        allow_dirty: bool = False,
    ) -> GitCheckoutResult:
        """Fetch the declared revision and move the worktree to it detached."""

        return self.checkout_detached(
            worktree,
            repository,
            subdirectory=subdirectory,
            allow_dirty=allow_dirty,
            fetch=True,
        )


__all__ = ("GitCheckoutResult", "GitSourceAdapter", "GitSourceError")
