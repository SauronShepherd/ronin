"""Content-addressed local artifact persistence for durable execution evidence."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    role: str
    digest_algorithm: str
    digest: str
    media_type: str | None
    size_bytes: int
    storage_ref: str


class ArtifactIntegrityError(ValueError):
    """Raised when persisted artifact content no longer matches its digest."""


@dataclass(frozen=True, slots=True)
class ArtifactPage:
    """Bounded artifact inventory page with an opaque local cursor."""

    digests: tuple[str, ...]
    next_cursor: str | None
    truncated: bool

    def __post_init__(self) -> None:
        if any(
            len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            for digest in self.digests
        ):
            raise ValueError("artifact page contains an invalid SHA-256 digest")
        if self.next_cursor is not None and not self.next_cursor:
            raise ValueError("artifact page cursor must be non-empty when present")
        if self.truncated != (self.next_cursor is not None):
            raise ValueError("truncated artifact page must have exactly one cursor")


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, *, role: str, data: bytes, media_type: str | None = None) -> ArtifactRef:
        if not role or role != role.strip() or "\n" in role or "\r" in role:
            raise ValueError("artifact role must be non-empty, trimmed, and single-line")
        digest = hashlib.sha256(data).hexdigest()
        target = self._path_for_digest(digest)
        needs_write = not target.exists()
        if not needs_write:
            existing = target.read_bytes()
            needs_write = (
                len(existing) != len(data) or hashlib.sha256(existing).hexdigest() != digest
            )
        if needs_write:
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        ref = ArtifactRef(
            role=role,
            digest_algorithm="sha256",
            digest=digest,
            media_type=media_type,
            size_bytes=len(data),
            storage_ref=f"artifact://sha256/{digest}",
        )
        if not self.verify(ref):
            raise ArtifactIntegrityError("artifact failed digest verification after write")
        return ref

    def get_bytes(self, ref: ArtifactRef) -> bytes:
        self._validate_ref(ref)
        data = self._path_for_digest(ref.digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != ref.digest:
            raise ArtifactIntegrityError("artifact digest verification failed")
        return data

    def get_bytes_by_storage_ref(self, storage_ref: str, *, digest: str) -> bytes:
        if storage_ref != f"artifact://sha256/{digest}":
            raise ValueError("artifact storage_ref does not match local digest")
        data = self._path_for_digest(digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ArtifactIntegrityError("artifact digest verification failed")
        return data

    def verify(self, ref: ArtifactRef) -> bool:
        try:
            data = self.get_bytes(ref)
        except (FileNotFoundError, ArtifactIntegrityError, ValueError):
            return False
        return len(data) == ref.size_bytes

    def delete(self, ref: ArtifactRef) -> bool:
        """Delete one validated content-addressed artifact if it exists."""

        self._validate_ref(ref)
        target = self._path_for_digest(ref.digest)
        try:
            target.unlink()
        except FileNotFoundError:
            return False
        return True

    def list_digests(self) -> tuple[str, ...]:
        """List stored SHA-256 digests in deterministic order."""

        root = self._root / "sha256"
        if not root.is_dir():
            return ()
        return tuple(
            sorted(
                path.name
                for prefix in root.iterdir()
                if prefix.is_dir() and len(prefix.name) == 2
                for path in prefix.iterdir()
                if path.is_file()
                and len(path.name) == 64
                and all(char in "0123456789abcdef" for char in path.name)
            )
        )

    def list_digests_page(
        self, *, cursor: str | None = None, page_size: int = 1000
    ) -> ArtifactPage:
        if page_size < 1 or page_size > 10_000:
            raise ValueError("artifact discovery page_size must be between 1 and 10000")
        offset = 0
        if cursor is not None:
            try:
                offset = int(cursor)
            except ValueError as exc:
                raise ValueError("artifact discovery cursor is invalid") from exc
            if offset < 0:
                raise ValueError("artifact discovery cursor is invalid")
        digests = self.list_digests()
        page = digests[offset : offset + page_size]
        truncated = offset + len(page) < len(digests)
        return ArtifactPage(page, str(offset + len(page)) if truncated else None, truncated)

    def storage_ref_for_digest(self, digest: str) -> str:
        self._path_for_digest(digest)
        return f"artifact://sha256/{digest}"

    def _validate_ref(self, ref: ArtifactRef) -> None:
        if ref.digest_algorithm != "sha256":
            raise ValueError("unsupported artifact digest algorithm")
        if len(ref.digest) != 64 or any(char not in "0123456789abcdef" for char in ref.digest):
            raise ValueError("artifact digest must be lowercase sha256 hex")
        if ref.storage_ref != f"artifact://sha256/{ref.digest}":
            raise ValueError("artifact storage_ref does not match digest")

    def _path_for_digest(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid artifact digest")
        return self._root / "sha256" / digest[:2] / digest


__all__ = ["ArtifactIntegrityError", "ArtifactPage", "ArtifactRef", "LocalArtifactStore"]
