"""Provider-neutral source revision policy at the Git adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .git import GitCaptureError, GitRevision, capture_revision


class SourcePolicyError(ValueError):
    """Raised when a source URI or local revision violates project policy."""


@dataclass(frozen=True, slots=True)
class SourceRevisionEvidence:
    uri: str
    revision: GitRevision
    dirty_allowed: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "commit": self.revision.commit,
            "dirty_patch_sha256": self.revision.dirty_patch_sha256,
            "dirty_allowed": self.dirty_allowed,
        }


def validate_repository_uri(uri: str) -> str:
    """Validate a credential-free Git URI and return its canonical text."""
    if not isinstance(uri, str) or not uri or uri.strip() != uri:
        raise SourcePolicyError("repository URI must be non-empty and trimmed")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in uri):
        raise SourcePolicyError("repository URI must not contain control characters")
    parsed = urlsplit(uri)
    if parsed.password is not None or (parsed.username is not None and parsed.scheme != "ssh"):
        raise SourcePolicyError("repository URI must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SourcePolicyError("repository URI must not contain query or fragment")
    if parsed.scheme not in {"https", "ssh", "git", "file"}:
        raise SourcePolicyError("repository URI scheme is unsupported")
    if parsed.scheme == "file" and parsed.netloc:
        raise SourcePolicyError("file repository URI must not identify a remote host")
    if parsed.scheme != "file" and not parsed.netloc:
        raise SourcePolicyError("repository URI must identify a host")
    return uri


def capture_source_revision(
    uri: str, path: Path, *, allow_dirty: bool = False
) -> SourceRevisionEvidence:
    """Capture exact local Git identity, rejecting uncommitted state by default."""
    validated = validate_repository_uri(uri)
    try:
        revision = capture_revision(path)
    except GitCaptureError as exc:
        raise SourcePolicyError(str(exc)) from exc
    if revision.dirty_patch_sha256 is not None and not allow_dirty:
        raise SourcePolicyError(
            "source worktree is dirty; commit changes or explicitly allow dirty evidence"
        )
    return SourceRevisionEvidence(validated, revision, allow_dirty)


__all__ = (
    "SourcePolicyError",
    "SourceRevisionEvidence",
    "capture_source_revision",
    "validate_repository_uri",
)
