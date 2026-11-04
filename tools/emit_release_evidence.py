"""Emit one exact-candidate evidence receipt for a local/manual gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.release_evidence import SCHEMA, EvidenceError, validate_bundle


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
    execution_scope: str,
    fingerprint: str,
    command: str,
    artifacts: list[Path],
    reason: str | None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    names = [str(path.resolve()) for path in artifacts]
    record: dict[str, Any] = {
        "gate_id": gate_id,
        "status": status,
        "execution_scope": execution_scope,
        "commit": commit,
        "environment": {"fingerprint": fingerprint},
        "command": command,
        "started_at": started_at or now,
        "ended_at": ended_at or now,
    }
    if status in {"passed", "failed"}:
        record["artifacts"] = names
        record["artifact_digests"] = {
            name: sha256(path) for name, path in zip(names, artifacts, strict=True)
        }
    else:
        record["reason"] = reason or "local/manual qualification gate did not pass"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(prog="emit-release-evidence")
    parser.add_argument("--gate-id", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--status", choices=("passed", "failed", "skipped", "blocked"), required=True
    )
    parser.add_argument(
        "--execution-scope",
        choices=("complete", "diagnostic"),
        required=True,
        help="complete means the full declared gate ran; filtered/partial work is diagnostic",
    )
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument(
        "--profile",
        choices=("release_required", "local_mvp_required", "merge_required"),
        default="release_required",
    )
    parser.add_argument(
        "--started-at", required=True, help="ISO-8601 timestamp captured before the gate starts"
    )
    parser.add_argument(
        "--ended-at", required=True, help="ISO-8601 timestamp captured after the gate ends"
    )
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--reason")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.status in {"passed", "failed"} and not args.artifact:
        parser.error(f"--status {args.status} requires at least one --artifact report")
    try:
        record = build_record(
            gate_id=args.gate_id,
            commit=args.commit,
            status=args.status,
            execution_scope=args.execution_scope,
            fingerprint=args.fingerprint,
            command=args.command,
            artifacts=args.artifact,
            reason=args.reason,
            started_at=args.started_at,
            ended_at=args.ended_at,
        )
        bundle: dict[str, Any] = {
            "schema": SCHEMA,
            "commit": args.commit,
            "qualification_profile": args.profile,
            "generated_at": record["ended_at"],
            "records": [record],
        }
        validate_bundle(bundle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (EvidenceError, OSError) as exc:
        print(f"release evidence invalid: {exc}")
        return 2
    print(json.dumps(bundle, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
