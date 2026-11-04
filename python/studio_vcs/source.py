"""Provider-neutral source revision policy at the Git adapter boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from studio_core.source_control import safe_checkout_path

from .git import GitCaptureError, GitRevision, _git, _repository_root, capture_revision


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


def _repository_location(uri: str) -> tuple[str, str, int | None, str]:
    parsed = urlsplit(uri)
    if parsed.scheme == "file":
        raw_path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", raw_path):
            raw_path = raw_path[1:]
        path = Path(raw_path).resolve(strict=False)
        return ("file", "", None, str(path).casefold())
    return (
        "git",
        (parsed.hostname or "").casefold(),
        parsed.port,
        parsed.path.rstrip("/").removesuffix(".git"),
    )


def _verify_local_binding(uri: str, path: Path, subdirectory: str | None) -> None:
    try:
        root = _repository_root(path)
        configured_urls = _git(root, "remote", "get-url", "--all", "origin")
        urls = tuple(
            line.decode("utf-8").strip() for line in configured_urls.splitlines() if line.strip()
        )
        expected_location = _repository_location(uri)
        matching_remote = any(
            _repository_location(validate_repository_uri(remote)) == expected_location
            for remote in urls
        )
        expected_path = safe_checkout_path(root, subdirectory or "")
    except (GitCaptureError, OSError, TypeError, ValueError, UnicodeError) as exc:
        raise SourcePolicyError(
            "declared Git source could not be verified against the local checkout"
        ) from exc
    if not matching_remote:
        raise SourcePolicyError("declared Git source does not match the local origin remote")
    if expected_path != path.resolve():
        raise SourcePolicyError("project path does not match the declared repository subdirectory")


def capture_source_revision(
    uri: str,
    path: Path,
    *,
    subdirectory: str | None = None,
    allow_dirty: bool = False,
) -> SourceRevisionEvidence:
    """Verify the local source binding and capture its exact Git identity."""
    validated = validate_repository_uri(uri)
    _verify_local_binding(validated, path, subdirectory)
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
