"""Read-only local Git revision capture."""

from __future__ import annotations

import hashlib
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


def _untracked_digest_input(root: Path) -> bytes:
    names = [
        value.decode("utf-8", errors="surrogateescape")
        for value in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
        if value
    ]
    chunks: list[bytes] = []
    for name in sorted(names):
        relative = Path(name)
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise GitCaptureError("untracked path escapes or cannot be resolved") from exc
        if candidate.is_symlink() or not candidate.is_file():
            raise GitCaptureError("untracked special files cannot be captured")
        data = candidate.read_bytes()
        normalized = relative.as_posix().encode("utf-8", errors="surrogateescape")
        chunks.extend(
            (
                normalized,
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
    commit = _git(root, "rev-parse", "HEAD").decode("ascii").strip().lower()
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if not status:
        return GitRevision(commit)
    tracked_diff = _git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--")
    untracked = _untracked_digest_input(root)
    digest = hashlib.sha256(
        b"ronin/git-dirty-v1\0" + tracked_diff + b"\0untracked\0" + untracked
    ).hexdigest()
    return GitRevision(commit, digest)


__all__ = ("GitCaptureError", "GitRevision", "capture_revision")
