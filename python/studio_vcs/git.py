"""Read-only local Git revision capture."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitCaptureError(RuntimeError):
    """Raised when a local repository revision cannot be captured safely."""


@dataclass(frozen=True, slots=True)
class GitRevision:
    commit: str
    dirty_patch_sha256: str | None = None

    def __post_init__(self) -> None:
        if len(self.commit) not in {40, 64} or any(
            char not in "0123456789abcdef" for char in self.commit
        ):
            raise ValueError("commit must be a lowercase 40- or 64-character Git object id")
        if self.dirty_patch_sha256 is not None and (
            len(self.dirty_patch_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.dirty_patch_sha256)
        ):
            raise ValueError("dirty patch digest must be lowercase SHA-256 hex")


def checkout_detached(path: Path, commit: str) -> GitRevision:
    """Checkout an exact commit only from a clean local worktree.

    The caller owns the worktree lifecycle; this adapter never resets or cleans
    files, so a dirty tree fails closed rather than risking data loss.
    """
    if (
        not isinstance(commit, str)
        or len(commit) not in {40, 64}
        or commit != commit.lower()
        or any(char not in "0123456789abcdef" for char in commit)
    ):
        raise GitCaptureError("commit must be a lowercase 40- or 64-character Git object id")
    root = _repository_root(path)
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status:
        raise GitCaptureError("cannot checkout a revision from a dirty worktree")
    _git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    _git(root, "checkout", "--detach", commit)
    actual = _git(root, "rev-parse", "HEAD").decode("ascii").strip().lower()
    if actual != commit:
        raise GitCaptureError("Git checkout did not resolve to the requested commit")
    return GitRevision(actual)


def create_branch(path: Path, branch: str, *, start_commit: str | None = None) -> GitRevision:
    """Create a local branch from a validated commit without touching dirty trees."""
    if not isinstance(branch, str) or not branch.strip() or branch != branch.strip():
        raise GitCaptureError("branch must be a non-empty trimmed name")
    root = _repository_root(path)
    try:
        _git(root, "check-ref-format", "--branch", branch)
    except GitCaptureError as exc:
        raise GitCaptureError("branch name is invalid") from exc
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status:
        raise GitCaptureError("cannot create a branch from a dirty worktree")
    revision = start_commit or _git(root, "rev-parse", "HEAD").decode("ascii").strip().lower()
    if (
        len(revision) not in {40, 64}
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise GitCaptureError("start_commit must be a lowercase Git object id")
    _git(root, "cat-file", "-e", f"{revision}^{{commit}}")
    _git(root, "branch", branch, revision)
    return GitRevision(revision)


def delete_branch(path: Path, branch: str) -> None:
    """Delete only a fully merged local branch from a clean worktree."""
    if not isinstance(branch, str) or not branch.strip() or branch != branch.strip():
        raise GitCaptureError("branch must be a non-empty trimmed name")
    root = _repository_root(path)
    try:
        _git(root, "check-ref-format", "--branch", branch)
    except GitCaptureError as exc:
        raise GitCaptureError("branch name is invalid") from exc
    current = _git(root, "symbolic-ref", "--short", "HEAD").decode("utf-8").strip()
    if current == branch:
        raise GitCaptureError("cannot delete the current branch")
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status:
        raise GitCaptureError("cannot delete a branch from a dirty worktree")
    _git(root, "branch", "-d", branch)


def fetch_updates(path: Path, *, remote: str = "origin") -> GitRevision:
    """Fetch remote refs without changing the checked-out worktree."""
    if not isinstance(remote, str) or not remote.strip() or remote != remote.strip():
        raise GitCaptureError("remote must be a non-empty trimmed name")
    root = _repository_root(path)
    if any(character in remote for character in ("/", "\\", "\x00")):
        raise GitCaptureError("remote name is invalid")
    _git(root, "remote", "get-url", remote)
    _git(root, "fetch", "--prune", "--no-tags", remote)
    commit = _git(root, "rev-parse", "HEAD").decode("ascii").strip().lower()
    return GitRevision(commit)


def _git(path: Path, *args: str, timeout: float = 10.0) -> bytes:
    location = path if path.is_dir() else path.parent
    command = ("git", "--no-optional-locks", "-C", str(location), *args)
    try:
        completed = subprocess.run(  # noqa: S603
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitCaptureError("Git command could not be executed") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        detail = detail.splitlines()[0][:200] if detail else "Git command failed"
        raise GitCaptureError(detail)
    return completed.stdout


def _repository_root(path: Path) -> Path:
    raw = _git(path, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    root = Path(raw).resolve()
    if not root.is_dir():
        raise GitCaptureError("Git repository root is not a directory")
    return root


def _normalized_untracked_mode(metadata: os.stat_result) -> bytes:
    """Encode the same owner-executable distinction Git stores for regular files."""
    if os.name == "posix" and metadata.st_mode & stat.S_IXUSR:
        return b"100755"
    return b"100644"


def _untracked_digest_input(root: Path, pathspec: tuple[str, ...] = ()) -> bytes:
    ls_args = ("ls-files", "--others", "--exclude-standard", "-z", "--", *pathspec)
    names = [
        value.decode("utf-8", errors="surrogateescape")
        for value in _git(root, *ls_args).split(b"\0")
        if value
    ]
    chunks: list[bytes] = []
    for name in sorted(names):
        relative = Path(name)
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
            metadata = candidate.lstat()
        except (OSError, ValueError) as exc:
            raise GitCaptureError("untracked path escapes or cannot be resolved") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise GitCaptureError("untracked special files cannot be captured")
        try:
            data = candidate.read_bytes()
        except OSError as exc:
            raise GitCaptureError("untracked file cannot be read") from exc
        normalized = relative.as_posix().encode("utf-8", errors="surrogateescape")
        mode = _normalized_untracked_mode(metadata)
        chunks.extend(
            (
                normalized,
                b"\0",
                mode,
                b"\0",
                str(len(data)).encode("ascii"),
                b"\0",
                hashlib.sha256(data).digest(),
                b"\0",
            )
        )
    return b"".join(chunks)


def capture_revision(path: Path) -> GitRevision:
    """Capture commit plus a deterministic digest for tracked and untracked dirtiness."""
    root = _repository_root(path)
    resolved_path = path.resolve()
    if resolved_path == root:
        pathspec: tuple[str, ...] = ()
    else:
        try:
            pathspec = (resolved_path.relative_to(root).as_posix(),)
        except ValueError as exc:
            raise GitCaptureError("path is outside the Git repository") from exc
    commit = _git(root, "rev-parse", "HEAD").decode("ascii").strip().lower()
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        *pathspec,
    )
    if not status:
        return GitRevision(commit)
    tracked_diff = _git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--", *pathspec)
    untracked = _untracked_digest_input(root, pathspec)
    digest = hashlib.sha256(
        b"ronin/git-dirty-v1\0" + tracked_diff + b"\0untracked\0" + untracked
    ).hexdigest()
    return GitRevision(commit, digest)


__all__ = (
    "GitCaptureError",
    "GitRevision",
    "capture_revision",
    "checkout_detached",
    "create_branch",
    "delete_branch",
    "fetch_updates",
)
