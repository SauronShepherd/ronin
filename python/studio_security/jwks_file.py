"""Bounded local-file JWKS adapter for deterministic OIDC server composition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

_MAX_JWKS_BYTES = 1024 * 1024


class JwksFileError(RuntimeError):
    """Raised when a configured JWKS file cannot be read or validated."""


class FileJwksProvider:
    """Read one bounded JWKS document from disk on every access.

    Re-reading allows atomic file replacement to rotate signing keys without
    keeping network or mutable refresh state inside the security validator.
    """

    def __init__(self, path: Path, *, max_bytes: int = _MAX_JWKS_BYTES) -> None:
        if max_bytes < 1 or max_bytes > _MAX_JWKS_BYTES:
            raise ValueError(f"JWKS max_bytes must be between 1 and {_MAX_JWKS_BYTES}")
        self._path = path.expanduser().resolve()
        self._max_bytes = max_bytes

    @property
    def path(self) -> Path:
        return self._path

    def jwks(self) -> dict[str, object]:
        try:
            size = self._path.stat().st_size
        except OSError as exc:
            raise JwksFileError("OIDC JWKS file is not readable") from exc
        if size > self._max_bytes:
            raise JwksFileError("OIDC JWKS file exceeds configured byte limit")
        try:
            raw = self._path.read_bytes()
        except OSError as exc:
            raise JwksFileError("OIDC JWKS file is not readable") from exc
        if len(raw) > self._max_bytes:
            raise JwksFileError("OIDC JWKS file exceeds configured byte limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JwksFileError("OIDC JWKS file must contain valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise JwksFileError("OIDC JWKS document must be a JSON object")
        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise JwksFileError("OIDC JWKS document must contain a keys array")
        if not all(isinstance(item, dict) for item in keys):
            raise JwksFileError("OIDC JWKS keys array must contain only JSON objects")
        return cast(dict[str, object], payload)


__all__ = ("FileJwksProvider", "JwksFileError")
