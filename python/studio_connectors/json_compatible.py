"""Lossless, bounded JSON projection for values returned by database connectors."""

from __future__ import annotations

import base64
import datetime as dt
import math
import uuid
from decimal import Decimal

_MAX_NESTING = 64
_MAX_SAFE_INTEGER = (2**53) - 1


def json_compatible(value: object, *, depth: int = 0) -> object:
    """Convert common database scalars to JSON values without float precision loss.

    Decimal and integers outside JavaScript's exact integer range become decimal
    strings; the enclosing field schema carries their original database type.
    """
    if depth > _MAX_NESTING:
        raise ValueError("connector value exceeds maximum JSON nesting depth")
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value if -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER else str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("connector values must not contain non-finite numbers")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("connector values must not contain non-finite decimals")
        return str(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("connector JSON object keys must be text")
        return {key: json_compatible(child, depth=depth + 1) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [json_compatible(child, depth=depth + 1) for child in value]
    raise ValueError(f"unsupported connector JSON value type: {type(value).__name__}")


__all__ = ("json_compatible",)
