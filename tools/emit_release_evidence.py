"""Emit one exact-candidate release-evidence bundle for a workflow gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.release_evidence import SCHEMA, validate_bundle


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_record(
    *,
    gate_id: str,
    commit: str,
    status: str,
    fingerprint: str,
    command: str,
    artifacts: list[Path],
    reason: str | None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    names = [str(path) for path in artifacts]
    record: dict[str, Any] = {
        "gate_id": gate_id,
        "status": status,
        "commit": commit,
        "environment": {"fingerprint": fingerprint},
        "command": command,
        "started_at": now,
        "ended_at": now,
    }
    if status == "passed":
        record["artifacts"] = names
        record["artifact_digests"] = {
            name: sha256(path) for name, path in zip(names, artifacts, strict=True)
        }
    else:
        record["reason"] = reason or "workflow gate did not pass"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(prog="emit-release-evidence")
    parser.add_argument("--gate-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--status", choices=("passed", "failed", "skipped", "blocked"), required=True
    )
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--reason")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = build_record(
        gate_id=args.gate_id,
        commit=args.commit,
        status=args.status,
        fingerprint=args.fingerprint,
        command=args.command,
        artifacts=args.artifact,
        reason=args.reason,
    )
    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "commit": args.commit,
        "generated_at": record["ended_at"],
        "records": [record],
    }
    validate_bundle(bundle)
    args.output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(bundle, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
