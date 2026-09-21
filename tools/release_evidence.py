"""Versioned, fail-closed release qualification evidence.

The manifest records what was actually executed.  A skipped external gate is
never interpreted as a pass and every pass is bound to an exact source and
environment identity.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "ronin.release-evidence/v1"
STATUSES = {"passed", "failed", "skipped", "blocked"}
REQUIRED = {"gate_id", "status", "commit", "environment", "command", "started_at", "ended_at"}


class EvidenceError(ValueError):
    """Raised when evidence cannot support a release claim."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{name} must be a non-empty string")
    return value.strip()


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise EvidenceError("evidence record must be an object")
    missing = sorted(REQUIRED - record.keys())
    if missing:
        raise EvidenceError("missing required fields: " + ", ".join(missing))
    gate_id = _text(record["gate_id"], "gate_id")
    status = _text(record["status"], "status")
    if status not in STATUSES:
        raise EvidenceError(f"unsupported status for {gate_id}: {status}")
    _text(record["commit"], "commit")
    _text(record["command"], "command")
    _text(record["started_at"], "started_at")
    _text(record["ended_at"], "ended_at")
    if not isinstance(record["environment"], dict):
        raise EvidenceError(f"environment must be an object for {gate_id}")
    if status == "passed":
        if not record["environment"].get("fingerprint"):
            raise EvidenceError(f"passed evidence requires environment.fingerprint: {gate_id}")
        if not record.get("artifacts"):
            raise EvidenceError(f"passed evidence requires artifacts: {gate_id}")
    if status in {"skipped", "blocked"}:
        reason = record.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise EvidenceError(f"{status} evidence requires reason: {gate_id}")
    return record


def validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, dict) or bundle.get("schema") != SCHEMA:
        raise EvidenceError(f"schema must be {SCHEMA}")
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise EvidenceError("records must be a non-empty array")
    seen: set[str] = set()
    for record in records:
        validated = validate_record(record)
        gate_id = validated["gate_id"]
        if gate_id in seen:
            raise EvidenceError(f"duplicate gate_id: {gate_id}")
        seen.add(gate_id)
    return bundle


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read evidence bundle {path}: {exc}") from exc
    return validate_bundle(value)


def merge(paths: list[Path]) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    commits: set[str] = set()
    for path in paths:
        bundle = load(path)
        for record in bundle["records"]:
            gate_id = record["gate_id"]
            if gate_id in records:
                raise EvidenceError(f"duplicate gate_id across bundles: {gate_id}")
            records[gate_id] = record
            commits.add(record["commit"])
    if len(commits) != 1:
        raise EvidenceError("all evidence records must target one commit")
    result = {
        "schema": SCHEMA,
        "commit": next(iter(commits)),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records": [records[key] for key in sorted(records)],
    }
    return validate_bundle(result)


def _main() -> int:
    parser = argparse.ArgumentParser(prog="release-evidence")
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("validate")
    check.add_argument("bundle", type=Path)
    combine = sub.add_parser("merge")
    combine.add_argument("output", type=Path)
    combine.add_argument("bundles", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        result = load(args.bundle) if args.action == "validate" else merge(args.bundles)
        if args.action == "merge":
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0
    except EvidenceError as exc:
        print(f"release evidence invalid: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
