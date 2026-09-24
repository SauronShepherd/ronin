"""Resolve governed JSON row artifacts for scheduler quality gates."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from studio_storage.ports import ArtifactStore

_REF = re.compile(r"^artifact://sha256/([0-9a-f]{64})$")


class QualityRowsReferenceError(ValueError):
    """Raised when a quality rows reference is not a verified JSON artifact."""


def resolve_quality_rows(rows_ref: str, store: ArtifactStore) -> tuple[Mapping[str, object], ...]:
    match = _REF.fullmatch(rows_ref)
    if match is None:
        raise QualityRowsReferenceError("quality rows_ref must be artifact://sha256/<digest>")
    digest = match.group(1)
    getter = getattr(store, "get_bytes_by_storage_ref", None)
    if getter is None:
        raise QualityRowsReferenceError("artifact store cannot resolve storage references")
    try:
        data = getter(rows_ref, digest=digest)
        payload = json.loads(data)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise QualityRowsReferenceError("quality rows artifact is not valid JSON") from exc
    if not isinstance(payload, list) or not all(isinstance(row, Mapping) for row in payload):
        raise QualityRowsReferenceError("quality rows artifact must contain an array of objects")
    return tuple(payload)


__all__ = ("QualityRowsReferenceError", "resolve_quality_rows")
