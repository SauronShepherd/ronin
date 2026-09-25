"""Versioned, fail-closed release qualification evidence.

The manifest records what was actually executed.  A skipped external gate is
never interpreted as a pass and every pass is bound to an exact source and
environment identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "ronin.release-evidence/v1"
STATUSES = {"passed", "failed", "skipped", "blocked"}
REQUIRED = {"gate_id", "status", "commit", "environment", "command", "started_at", "ended_at"}

# Gate classes are deliberately explicit.  Callers may add a narrower
# project-specific set, but a release verdict must never silently use the
# merge gate set as a substitute for the release gate set.
MERGE_REQUIRED_GATES = frozenset({"ci", "security", "status-consistency"})
RELEASE_REQUIRED_GATES = frozenset(
    {
        *MERGE_REQUIRED_GATES,
        "docker-qualification",
        "mutation",
        "browser",
        "a11y",
        "installed-artifact",
        "sbom-provenance",
        "license",
        "artifact-identity",
    }
)
GATE_PROFILES = {
    "merge_required": MERGE_REQUIRED_GATES,
    "release_required": RELEASE_REQUIRED_GATES,
}


class EvidenceError(ValueError):
    """Raised when evidence cannot support a release claim."""


def required_gates(profile: str) -> frozenset[str]:
    """Return the named gate profile, rejecting unknown profiles fail-closed."""

    try:
        return GATE_PROFILES[profile]
    except KeyError as exc:
        available = ", ".join(sorted(GATE_PROFILES))
        raise EvidenceError(f"unknown gate profile {profile!r}; choose from {available}") from exc


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
    started_at = _text(record["started_at"], "started_at")
    ended_at = _text(record["ended_at"], "ended_at")
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"timestamps must be ISO-8601 for {gate_id}") from exc
    if started.tzinfo is None or ended.tzinfo is None:
        raise EvidenceError(f"timestamps must include a timezone for {gate_id}")
    if ended < started:
        raise EvidenceError(f"ended_at must not precede started_at for {gate_id}")
    if not isinstance(record["environment"], dict):
        raise EvidenceError(f"environment must be an object for {gate_id}")
    if status == "passed":
        if not record["environment"].get("fingerprint"):
            raise EvidenceError(f"passed evidence requires environment.fingerprint: {gate_id}")
        artifacts = record.get("artifacts")
        if (
            not isinstance(artifacts, list)
            or not artifacts
            or not all(isinstance(item, str) and item.strip() for item in artifacts)
        ):
            raise EvidenceError(f"passed evidence requires artifacts: {gate_id}")
        digests = record.get("artifact_digests")
        if not isinstance(digests, dict) or not digests:
            raise EvidenceError(f"passed evidence requires artifact_digests: {gate_id}")
        missing_digests = [item for item in artifacts if item not in digests]
        if missing_digests:
            raise EvidenceError(
                f"passed evidence is missing artifact digests for {gate_id}: "
                + ", ".join(missing_digests)
            )
        extra_digests = sorted(set(digests) - set(artifacts))
        if extra_digests:
            raise EvidenceError(
                f"passed evidence has digests for undeclared artifacts for {gate_id}: "
                + ", ".join(extra_digests)
            )
        for artifact, digest in digests.items():
            if not isinstance(artifact, str) or not artifact.strip():
                raise EvidenceError(f"artifact_digests contains an invalid name: {gate_id}")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise EvidenceError(f"artifact_digests contains an invalid SHA-256: {gate_id}")
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
    if "commit" not in bundle:
        raise EvidenceError("bundle commit is required")
    bundle_commit = _text(bundle["commit"], "commit")
    seen: set[str] = set()
    for record in records:
        validated = validate_record(record)
        if bundle_commit is not None and validated["commit"] != bundle_commit:
            raise EvidenceError(
                f"bundle commit {bundle_commit!r} does not match gate {validated['gate_id']}"
            )
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
        "generated_at": datetime.now(UTC).isoformat(),
        "records": [records[key] for key in sorted(records)],
    }
    return validate_bundle(result)


def release_verdict(
    bundle: dict[str, Any], required_gates: set[str], *, expected_commit: str | None = None
) -> dict[str, Any]:
    """Return an authoritative verdict; missing/skipped/stale gates fail closed."""

    if (
        not isinstance(required_gates, set)
        or not required_gates
        or any(not isinstance(gate_id, str) or not gate_id.strip() for gate_id in required_gates)
    ):
        raise EvidenceError("required_gates must be a non-empty set of names")
    validated = validate_bundle(bundle)
    records = {record["gate_id"]: record for record in validated["records"]}
    commits = {record["commit"] for record in validated["records"]}
    if len(commits) != 1:
        raise EvidenceError("release verdict requires one exact commit")
    if validated.get("commit") != next(iter(commits)):
        raise EvidenceError("release verdict root commit does not match gate evidence")
    if expected_commit is not None and validated["commit"] != _text(
        expected_commit, "expected_commit"
    ):
        raise EvidenceError(
            f"release evidence commit {validated['commit']!r} does not match expected commit "
            f"{expected_commit!r}"
        )
    missing = sorted(required_gates - records.keys())
    non_passing = sorted(
        gate_id
        for gate_id in required_gates
        if gate_id in records and records[gate_id]["status"] != "passed"
    )
    if missing or non_passing:
        raise EvidenceError(
            f"release verdict is not green: missing={missing}, non_passing={non_passing}"
        )
    verdict = {
        "schema": "ronin.release-verdict/v1",
        "commit": validated["commit"],
        "required_gates": sorted(required_gates),
        "status": "passed",
        "evidence": {
            gate_id: {
                "artifacts": records[gate_id].get("artifacts", []),
                "artifact_digests": records[gate_id].get("artifact_digests", {}),
            }
            for gate_id in sorted(required_gates)
        },
    }
    canonical = json.dumps(verdict, sort_keys=True, separators=(",", ":")).encode("utf-8")
    verdict["verdict_sha256"] = hashlib.sha256(canonical).hexdigest()
    return verdict


def _main() -> int:
    parser = argparse.ArgumentParser(prog="release-evidence")
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("validate")
    check.add_argument("bundle", type=Path)
    combine = sub.add_parser("merge")
    combine.add_argument("output", type=Path)
    combine.add_argument("bundles", type=Path, nargs="+")
    verdict = sub.add_parser("verdict")
    verdict.add_argument("bundle", type=Path)
    required = verdict.add_mutually_exclusive_group(required=True)
    required.add_argument("--required-gate", action="append")
    required.add_argument("--profile", choices=sorted(GATE_PROFILES))
    verdict.add_argument(
        "--expected-commit",
        help="require the evidence bundle to target this exact source commit",
    )
    args = parser.parse_args()
    try:
        if args.action == "validate":
            result = load(args.bundle)
        elif args.action == "merge":
            result = merge(args.bundles)
        else:
            gates = (
                set(args.required_gate)
                if args.required_gate is not None
                else set(required_gates(args.profile))
            )
            result = release_verdict(
                load(args.bundle),
                gates,
                expected_commit=args.expected_commit,
            )
        if args.action == "merge":
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except EvidenceError as exc:
        print(f"release evidence invalid: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
