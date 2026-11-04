"""Bounded Git source operations behind a provider-neutral execution boundary."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from studio_core.source_control import SourceRepository, safe_checkout_path

_COMMIT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _git_environment() -> dict[str, str]:
    """Remove ambient Git overrides and implicit credential/prompt behavior."""

    environment = os.environ.copy()
    controlled = {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_GLOBAL",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "GIT_TERMINAL_PROMPT",
        "GCM_INTERACTIVE",
    }
    for name in tuple(environment):
        if name in controlled or name.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            environment.pop(name, None)
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
        }
    )
    return environment


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

    def _run(
        self,
        worktree: Path,
        *args: str,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> str:
        return self._run_result(worktree, *args, allowed_returncodes=allowed_returncodes)[1]

    def _run_result(
        self,
        worktree: Path,
        *args: str,
        allowed_returncodes: tuple[int, ...] = (0,),
    ) -> tuple[int, str]:
        executable = shutil.which("git")
        if executable is None:
            raise GitSourceError("Git executable is unavailable")
        try:
            result = subprocess.run(  # noqa: S603
                (
                    executable,
                    "-c",
                    "credential.helper=",
                    "-c",
                    f"core.hooksPath={os.devnull}",
                    "-C",
                    str(worktree),
                    *args,
                ),
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                stdin=subprocess.DEVNULL,
                env=_git_environment(),
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise GitSourceError(f"git operation failed: {' '.join(args)}") from exc
        if result.returncode not in allowed_returncodes:
            raise GitSourceError(f"git operation failed: {' '.join(args)}")
        return result.returncode, result.stdout.strip()

    def is_dirty(self, worktree: Path) -> bool:
        return bool(self._run(worktree, "status", "--porcelain", "--untracked-files=all"))

    def fetch(self, worktree: Path, repository: SourceRepository) -> str:
        self._run(worktree, "fetch", "--no-tags", "--prune", repository.uri, repository.revision)
        return self._resolve_commit(worktree, "FETCH_HEAD")

    def fetch_revision(self, worktree: Path, repository: SourceRepository) -> str:
        """Fetch and resolve a source commit without changing the current checkout."""

        root = worktree.resolve()
        if self.is_dirty(root):
            raise GitSourceError("refusing source fetch in a dirty worktree")
        return self.fetch(root, repository)

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

    def fast_forward(
        self,
        worktree: Path,
        repository: SourceRepository,
        *,
        subdirectory: str = "",
    ) -> GitCheckoutResult:
        """Fetch and fast-forward the current local branch without rewriting history."""

        root = worktree.resolve()
        checkout_path = safe_checkout_path(root, subdirectory)
        if self.is_dirty(root):
            raise GitSourceError("refusing fast-forward in a dirty worktree")
        branch_status, branch = self._run_result(
            root,
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
            allowed_returncodes=(0, 1),
        )
        if branch_status == 1 or not branch:
            raise GitSourceError("refusing fast-forward from a detached HEAD")
        current = self._resolve_commit(root, "HEAD")
        target = self.fetch(root, repository)
        ancestor_status, _ = self._run_result(
            root,
            "merge-base",
            "--is-ancestor",
            current,
            target,
            allowed_returncodes=(0, 1),
        )
        if ancestor_status == 1 and current != target:
            # The local branch may already be ahead of the declared source.
            # Keep it unchanged; never rewind it to the source commit.
            target_is_ancestor, _ = self._run_result(
                root,
                "merge-base",
                "--is-ancestor",
                target,
                current,
                allowed_returncodes=(0, 1),
            )
            if target_is_ancestor == 0:
                return GitCheckoutResult(
                    repository,
                    checkout_path,
                    current,
                    False,
                )
            raise GitSourceError(
                "refusing fast-forward because local and source histories diverged"
            )
        if current == target:
            return GitCheckoutResult(
                repository,
                checkout_path,
                current,
                False,
            )
        self._run(root, "merge", "--ff-only", target)
        actual = self._resolve_commit(root, "HEAD")
        if actual != target:
            raise GitSourceError("fast-forward did not reach the fetched source revision")
        return GitCheckoutResult(repository, checkout_path, actual, False)

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
        checkout_path = safe_checkout_path(root, subdirectory)
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
        return GitCheckoutResult(repository, checkout_path, commit, dirty)

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
