"""Least-privilege secret resolution for deployment-local ``secret://`` references."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

from studio_core import SecretRef

_MAX_SECRET_BYTES = 1024 * 1024


class SecretResolutionError(RuntimeError):
    """Raised when a secret reference cannot be resolved safely."""


@dataclass(frozen=True, slots=True, repr=False)
class SecretMaterial:
    """Opaque resolved bytes with deliberately redacted string representations."""

    _value: bytes

    def __post_init__(self) -> None:
        if not self._value:
            raise SecretResolutionError("resolved secret is empty")
        if len(self._value) > _MAX_SECRET_BYTES:
            raise SecretResolutionError("resolved secret exceeds the configured byte limit")

    def reveal_bytes(self) -> bytes:
        """Return secret bytes only at an authorized execution boundary."""

        return self._value

    def reveal_text(self, *, encoding: str = "utf-8") -> str:
        """Decode secret bytes only at an authorized execution boundary."""

        try:
            return self._value.decode(encoding)
        except UnicodeDecodeError as exc:
            raise SecretResolutionError("resolved secret is not valid text") from exc

    def __repr__(self) -> str:
        return "SecretMaterial(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class SecretResolver(Protocol):
    """Resolve one opaque reference without exposing discovery/list operations."""

    def resolve(self, reference: SecretRef) -> SecretMaterial: ...


def _reference_parts(reference: SecretRef, *, backend: str) -> tuple[str, ...]:
    parsed = urlsplit(reference.uri)
    if parsed.netloc != backend:
        raise SecretResolutionError(f"secret reference is not for the {backend} backend")
    raw = parsed.path.lstrip("/")
    if not raw:
        raise SecretResolutionError("secret reference is missing its backend key")
    decoded = unquote(raw)
    if decoded != decoded.strip() or "\x00" in decoded or "\\" in decoded:
        raise SecretResolutionError("secret backend key is invalid")
    parts = tuple(decoded.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise SecretResolutionError("secret backend key contains unsafe path components")
    return parts


class EnvironmentSecretResolver:
    """Resolve ``secret://env/NAME`` from an injected/environment mapping."""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def resolve(self, reference: SecretRef) -> SecretMaterial:
        parts = _reference_parts(reference, backend="env")
        if len(parts) != 1:
            raise SecretResolutionError("environment secret references require exactly one name")
        name = parts[0]
        value = self._environ.get(name)
        if value is None:
            raise SecretResolutionError("environment secret is unavailable")
        return SecretMaterial(value.encode("utf-8"))


class MountedFileSecretResolver:
    """Resolve ``secret://file/path`` under one configured mounted root."""

    def __init__(self, root: Path, *, max_secret_bytes: int = _MAX_SECRET_BYTES) -> None:
        if max_secret_bytes <= 0:
            raise ValueError("max_secret_bytes must be positive")
        self._root = root.expanduser().resolve()
        self._max_secret_bytes = max_secret_bytes

    def resolve(self, reference: SecretRef) -> SecretMaterial:
        parts = _reference_parts(reference, backend="file")
        candidate = self._root.joinpath(*parts)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise SecretResolutionError("secret file escapes the configured root") from exc

        current = self._root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise SecretResolutionError("secret file path must not contain symbolic links")
        try:
            stat_result = candidate.stat()
        except FileNotFoundError as exc:
            raise SecretResolutionError("secret file is unavailable") from exc
        if not candidate.is_file():
            raise SecretResolutionError("secret file reference must resolve to a regular file")
        if stat_result.st_size <= 0:
            raise SecretResolutionError("resolved secret is empty")
        if stat_result.st_size > self._max_secret_bytes:
            raise SecretResolutionError("secret file exceeds the configured byte limit")
        value = candidate.read_bytes()
        if len(value) != stat_result.st_size:
            raise SecretResolutionError("secret file changed while being resolved")
        return SecretMaterial(value)


class CompositeSecretResolver:
    """Dispatch references to explicitly configured backends; unsupported schemes fail closed."""

    def __init__(
        self,
        *,
        environment: EnvironmentSecretResolver | None = None,
        mounted_file: MountedFileSecretResolver | None = None,
    ) -> None:
        self._environment = environment
        self._mounted_file = mounted_file

    def resolve(self, reference: SecretRef) -> SecretMaterial:
        backend = urlsplit(reference.uri).netloc
        if backend == "env" and self._environment is not None:
            return self._environment.resolve(reference)
        if backend == "file" and self._mounted_file is not None:
            return self._mounted_file.resolve(reference)
        raise SecretResolutionError("secret backend is not configured")


__all__ = (
    "CompositeSecretResolver",
    "EnvironmentSecretResolver",
    "MountedFileSecretResolver",
    "SecretMaterial",
    "SecretResolutionError",
    "SecretResolver",
)
