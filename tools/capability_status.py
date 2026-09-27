"""Validate the machine-readable Public v1 capability/status manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STATUSES = {
    "implemented",
    "partial",
    "missing",
    "blocked",
    "human_decision",
    "qualification_pending",
}
SCHEMA_VERSION = 1


class CapabilityStatusError(ValueError):
    """Raised when a capability ledger is ambiguous or malformed."""


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise CapabilityStatusError("unsupported capability status schema")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise CapabilityStatusError("capabilities must be a non-empty array")
    seen: set[str] = set()
    for item in capabilities:
        if not isinstance(item, dict):
            raise CapabilityStatusError("capability entries must be objects")
        identifier = item.get("id")
        status = item.get("status")
        summary = item.get("summary")
        if not isinstance(identifier, str) or not identifier.strip():
            raise CapabilityStatusError("capability id must be non-empty")
        if identifier in seen:
            raise CapabilityStatusError(f"duplicate capability id: {identifier}")
        seen.add(identifier)
        if status not in STATUSES:
            raise CapabilityStatusError(f"invalid status for {identifier}: {status}")
        if not isinstance(summary, str) or not summary.strip():
            raise CapabilityStatusError(f"summary missing for {identifier}")
    return value


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityStatusError(f"cannot read manifest: {exc}") from exc
    return validate_manifest(value)


def validate_public_manifest(root: Path) -> dict[str, Any]:
    """Load the repository's canonical Public v1 ledger by root path."""
    return load(root / "docs" / "product" / "public-v1-status.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    load(args.manifest)
    print(f"capability status valid: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
