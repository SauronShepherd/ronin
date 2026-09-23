"""Portable, credential-free source repository identity contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = frozenset({"https", "ssh", "git", "file"})
_SENSITIVE = ("password=", "token=", "secret=", "access_token=", "-----begin ")


def _text(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{name} must be non-empty and single-line")
    return value


@dataclass(frozen=True, slots=True)
class SourceRepository:
    """Repository locator plus an immutable revision identity."""

    uri: str
    revision: str

    @staticmethod
    def validate_uri(uri: str) -> str:
        """Validate and return a credential-free repository URI."""

        value = _text(uri, "repository uri")
        if any(term in value.casefold() for term in _SENSITIVE):
            raise ValueError("repository uri must not contain credential material")
        parsed = urlsplit(value)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ValueError("repository uri scheme is not supported")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("repository uri must not embed credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("repository uri must not contain query or fragment")
        if not parsed.netloc and not parsed.path:
            raise ValueError("repository uri must identify a repository")
        return value

    def __post_init__(self) -> None:
        uri = _text(self.uri, "repository uri")
        revision = _text(self.revision, "source revision")
        SourceRepository.validate_uri(uri)
        if revision.startswith("-") or any(char.isspace() for char in revision):
            raise ValueError("source revision must be a stable ref or digest")
        object.__setattr__(self, "uri", uri)
        object.__setattr__(self, "revision", revision)

    def to_payload(self) -> dict[str, str]:
        return {"uri": self.uri, "revision": self.revision}


def safe_checkout_path(worktree: Any, subdirectory: str = "") -> Any:
    """Resolve a repository-relative checkout path without symlink/path escape."""

    root = worktree.resolve()
    raw = root / subdirectory
    current = root
    for part in subdirectory.replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError("checkout subdirectory must not traverse a symlink")
    candidate = raw.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("checkout subdirectory escapes the worktree") from exc
    return candidate


__all__ = ("SourceRepository", "safe_checkout_path")
