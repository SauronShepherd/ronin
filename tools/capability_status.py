"""Validate the machine-readable Public v1 capability and release status."""

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
    "out_of_scope",
}
QUALIFICATION_STATUSES = {"blocked", "qualification_pending", "passed"}
BLOCKER_STATUSES = {"blocked", "qualification_pending", "human_decision", "missing"}
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

    qualification_status = value.get("qualification_status")
    if qualification_status is not None:
        if (
            not isinstance(qualification_status, str)
            or qualification_status not in QUALIFICATION_STATUSES
        ):
            raise CapabilityStatusError("invalid qualification_status")
        checklist = value.get("release_decision_checklist")
        if not isinstance(checklist, str) or not checklist.strip():
            raise CapabilityStatusError("release_decision_checklist is required")
        blockers = value.get("blocking_conditions")
        if qualification_status == "blocked" and (not isinstance(blockers, list) or not blockers):
            raise CapabilityStatusError("blocked qualification requires blocking_conditions")
        if blockers is not None:
            if not isinstance(blockers, list):
                raise CapabilityStatusError("blocking_conditions must be an array")
            blocker_ids: set[str] = set()
            for blocker in blockers:
                if not isinstance(blocker, dict):
                    raise CapabilityStatusError("blocking condition entries must be objects")
                blocker_id = blocker.get("id")
                blocker_status = blocker.get("status")
                blocker_summary = blocker.get("summary")
                evidence = blocker.get("evidence")
                if not isinstance(blocker_id, str) or not blocker_id.strip():
                    raise CapabilityStatusError("blocking condition id must be non-empty")
                if blocker_id in blocker_ids:
                    raise CapabilityStatusError(f"duplicate blocking condition id: {blocker_id}")
                blocker_ids.add(blocker_id)
                if not isinstance(blocker_status, str) or blocker_status not in BLOCKER_STATUSES:
                    raise CapabilityStatusError(
                        f"invalid status for blocking condition {blocker_id}"
                    )
                if not isinstance(blocker_summary, str) or not blocker_summary.strip():
                    raise CapabilityStatusError(
                        f"summary missing for blocking condition {blocker_id}"
                    )
                if not isinstance(evidence, str) or not evidence.strip():
                    raise CapabilityStatusError(
                        f"evidence missing for blocking condition {blocker_id}"
                    )
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
