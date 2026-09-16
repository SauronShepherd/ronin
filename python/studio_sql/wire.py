"""Stable JSON representation for values returned by SQL engines."""

from __future__ import annotations

import base64
import math
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID


def sql_wire_value(value: object) -> object:
    """Convert a backend scalar to the Public v1 JSON scalar contract."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("SQL result contains a non-finite number")
        return value
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    raise TypeError(f"unsupported SQL result scalar: {type(value).__name__}")


__all__ = ("sql_wire_value",)
