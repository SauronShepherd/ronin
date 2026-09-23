"""Validate candidate-bound evidence for a vendor migration certification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "ronin.migration-certification/v1"
PROFILES = frozenset({"fabric", "databricks", "foundry", "dataiku"})
STATUSES = frozenset(
    {"exact", "translated", "partial", "passthrough", "unsupported", "manual_decision"}
)


class CertificationError(ValueError):
    pass


def _digest(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise CertificationError(f"{name} must be a lowercase SHA-256 digest")
    return value


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != SCHEMA:
        raise CertificationError(f"schema must be {SCHEMA}")
    profile = payload.get("profile")
    if profile not in PROFILES:
        raise CertificationError("profile must be one of the certified migration profiles")
    _digest(payload.get("source_inventory_digest"), "source_inventory_digest")
    _digest(payload.get("report_digest"), "report_digest")
    _digest(payload.get("bundle_roundtrip_digest"), "bundle_roundtrip_digest")
    if payload.get("execution_status") != "passed":
        raise CertificationError("execution_status must be passed")
    counts = payload.get("classification_counts")
    if not isinstance(counts, dict) or set(counts) != STATUSES:
        raise CertificationError("classification_counts must contain every migration status")
    if any(not isinstance(value, int) or value < 0 for value in counts.values()):
        raise CertificationError("classification counts must be non-negative integers")
    if sum(counts.values()) == 0:
        raise CertificationError("certification must classify at least one source object")
    source_object_ids = payload.get("source_object_ids")
    if (
        not isinstance(source_object_ids, list)
        or not source_object_ids
        or not all(isinstance(value, str) and value.strip() for value in source_object_ids)
        or len(set(source_object_ids)) != len(source_object_ids)
    ):
        raise CertificationError(
            "source_object_ids must be a non-empty array of unique object identities"
        )
    if len(source_object_ids) != sum(counts.values()):
        raise CertificationError("source_object_ids count must equal the classified object count")
    classifications = payload.get("classifications")
    if (
        not isinstance(classifications, list)
        or len(classifications) != len(source_object_ids)
        or not all(isinstance(item, dict) for item in classifications)
    ):
        raise CertificationError("classifications must contain one entry for every source object")
    classified_ids: list[str] = []
    observed_counts = dict.fromkeys(STATUSES, 0)
    for item in classifications:
        object_id = item.get("source_object_id")
        status = item.get("status")
        if not isinstance(object_id, str) or not object_id.strip():
            raise CertificationError("classification source_object_id must be non-empty")
        if status not in STATUSES:
            raise CertificationError("classification status is unsupported")
        classified_ids.append(object_id)
        observed_counts[status] += 1
    if len(set(classified_ids)) != len(classified_ids):
        raise CertificationError("classification source_object_ids must be unique")
    if set(classified_ids) != set(source_object_ids):
        raise CertificationError("classifications must cover the source object inventory")
    if observed_counts != counts:
        raise CertificationError("classification entries must match classification_counts")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    validate(payload)
    print(f"migration certification valid: {payload['profile']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
