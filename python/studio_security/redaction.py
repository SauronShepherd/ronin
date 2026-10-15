"""Bounded recursive redaction for logs, evidence and provider metadata."""

from __future__ import annotations

from collections.abc import Mapping

_SECRET_TERMS = (
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "client_secret",
)
_REDACTED = "[REDACTED]"


def redact(value: object, *, max_depth: int = 8, max_items: int = 1000) -> object:
    """Return a deterministic copy with secret-like fields removed from output."""
    if max_depth < 0 or max_items < 1:
        raise ValueError("redaction bounds are invalid")
    return _redact(value, depth=max_depth, max_items=max_items)


def _redact(value: object, *, depth: int, max_items: int) -> object:
    if depth == 0:
        return "[TRUNCATED]" if isinstance(value, (Mapping, list, tuple)) else value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["[TRUNCATED_ITEMS]"] = max_items
                break
            name = str(key)
            result[name] = (
                _REDACTED
                if any(term in name.casefold() for term in _SECRET_TERMS)
                else _redact(item, depth=depth - 1, max_items=max_items)
            )
        return result
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth=depth - 1, max_items=max_items) for item in value[:max_items]]
    return value


__all__ = ("redact",)
