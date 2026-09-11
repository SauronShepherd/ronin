"""Canonical JSON bytes for Ronin identity-bearing v1 payloads."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import TypeAlias, cast

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _validate(value: object) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON numbers must be finite")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            _validate(child)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            _validate(child)
        return
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def encode(payload: object) -> bytes:
    """Return the exact UTF-8 canonical bytes used by Ronin v1 identity payloads."""

    _validate(payload)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate canonical JSON object member: {key}")
        value[key] = child
    return value


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite canonical JSON number is not allowed: {value}")


def decode(payload: str | bytes | bytearray) -> JSONValue:
    """Parse canonical-boundary JSON while rejecting duplicate and non-finite numbers."""

    try:
        value = json.loads(
            payload,
            object_pairs_hook=_object_from_pairs,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("canonical JSON payload is invalid") from exc
    _validate(value)
    return cast(JSONValue, value)


__all__ = ("JSONScalar", "JSONValue", "decode", "encode")
