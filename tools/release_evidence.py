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
EXECUTION_SCOPES = {"complete", "diagnostic"}
REQUIRED = {"gate_id", "status", "commit", "environment", "command", "started_at", "ended_at"}

# Gate classes are deliberately explicit.  Callers may add a narrower
# project-specific set, but a release verdict must never silently use the
# merge gate set as a substitute for the release gate set.
MERGE_REQUIRED_GATES = frozenset({"local-quality", "security", "status-consistency"})
RELEASE_REQUIRED_GATES = frozenset(
    {
        *MERGE_REQUIRED_GATES,
        "docker-qualification",
        "browser",
        "a11y",
        "installed-artifact",
        "sbom-provenance",
        "license",
        "artifact-identity",
    }
)
LOCAL_MVP_REQUIRED_GATES = RELEASE_REQUIRED_GATES
GATE_PROFILES = {
    "merge_required": MERGE_REQUIRED_GATES,
    "release_required": RELEASE_REQUIRED_GATES,
    "local_mvp_required": LOCAL_MVP_REQUIRED_GATES,
}
MAX_EVIDENCE_AGE_SECONDS = 24 * 60 * 60


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
    execution_scope = record.get("execution_scope")
    if execution_scope is not None and (
        not isinstance(execution_scope, str) or execution_scope not in EXECUTION_SCOPES
    ):
        raise EvidenceError(f"unsupported execution_scope for {gate_id}: {execution_scope!r}")
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
    if status in {"passed", "failed"}:
        if not record["environment"].get("fingerprint"):
            raise EvidenceError(f"{status} evidence requires environment.fingerprint: {gate_id}")
        artifacts = record.get("artifacts")
        if (
            not isinstance(artifacts, list)
            or not artifacts
            or not all(isinstance(item, str) and item.strip() for item in artifacts)
        ):
            raise EvidenceError(f"{status} evidence requires artifacts: {gate_id}")
        if len(set(artifacts)) != len(artifacts):
            raise EvidenceError(f"{status} evidence contains duplicate artifacts: {gate_id}")
        digests = record.get("artifact_digests")
        if not isinstance(digests, dict) or not digests:
            raise EvidenceError(f"{status} evidence requires artifact_digests: {gate_id}")
        invalid_digest_names = [
            artifact
            for artifact in digests
            if not isinstance(artifact, str) or not artifact.strip()
        ]
        if invalid_digest_names:
            raise EvidenceError(f"artifact_digests contains an invalid name: {gate_id}")
        missing_digests = [item for item in artifacts if item not in digests]
        if missing_digests:
            raise EvidenceError(
                f"{status} evidence is missing artifact digests for {gate_id}: "
                + ", ".join(missing_digests)
            )
        extra_digests = sorted(set(digests) - set(artifacts))
        if extra_digests:
            raise EvidenceError(
                f"{status} evidence has digests for undeclared artifacts for {gate_id}: "
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
    profile = bundle.get("qualification_profile")
    if profile is not None and (not isinstance(profile, str) or profile not in GATE_PROFILES):
        raise EvidenceError(f"unknown qualification_profile: {profile!r}")
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
    profiles: list[str | None] = []
    for path in paths:
        bundle = load(path)
        profiles.append(bundle.get("qualification_profile"))
        for record in bundle["records"]:
            gate_id = record["gate_id"]
            if gate_id in records:
                raise EvidenceError(f"duplicate gate_id across bundles: {gate_id}")
            records[gate_id] = record
            commits.add(record["commit"])
    if len(commits) != 1:
        raise EvidenceError("all evidence records must target one commit")
    if any(profile != profiles[0] for profile in profiles[1:]):
        raise EvidenceError("all evidence bundles must target one qualification profile")
    result = {
        "schema": SCHEMA,
        "commit": next(iter(commits)),
        "generated_at": datetime.now(UTC).isoformat(),
        "records": [records[key] for key in sorted(records)],
    }
    if profiles[0] is not None:
        result["qualification_profile"] = profiles[0]
    return validate_bundle(result)


def verify_artifacts(bundle: dict[str, Any]) -> None:
    """Re-hash each archived artifact before an aggregate can authorize release."""

    validated = validate_bundle(bundle)
    for record in validated["records"]:
        if record["status"] not in {"passed", "failed"}:
            continue
        for artifact in record.get("artifacts", []):
            path = Path(artifact)
            if not path.is_absolute():
                raise EvidenceError(
                    f"artifact path must be absolute for archived evidence: {artifact}"
                )
            if not path.is_file():
                raise EvidenceError(f"evidence artifact is missing: {artifact}")
            digest_state = hashlib.sha256()
            try:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest_state.update(chunk)
            except OSError as exc:
                raise EvidenceError(f"cannot read evidence artifact {artifact}: {exc}") from exc
            digest = digest_state.hexdigest()
            if record["artifact_digests"].get(artifact) != digest:
                raise EvidenceError(f"evidence artifact digest mismatch: {artifact}")


def release_verdict(
    bundle: dict[str, Any],
    required_gates: set[str],
    *,
    expected_commit: str | None = None,
    expected_profile: str | None = None,
) -> dict[str, Any]:
    """Return an authoritative verdict; missing/skipped/stale gates fail closed."""

    if (
        not isinstance(required_gates, set)
        or not required_gates
        or any(not isinstance(gate_id, str) or not gate_id.strip() for gate_id in required_gates)
    ):
        raise EvidenceError("required_gates must be a non-empty set of names")
    validated = validate_bundle(bundle)
    if expected_profile is not None:
        if expected_profile not in GATE_PROFILES:
            raise EvidenceError(f"unknown qualification profile {expected_profile!r}")
        if frozenset(required_gates) != GATE_PROFILES[expected_profile]:
            raise EvidenceError(
                f"required gates do not match qualification profile {expected_profile!r}"
            )
        if validated.get("qualification_profile") != expected_profile:
            raise EvidenceError(
                f"evidence profile {validated.get('qualification_profile')!r} does not match "
                f"expected profile {expected_profile!r}"
            )
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
    incomplete_scope = sorted(
        gate_id
        for gate_id in required_gates
        if gate_id in records
        and (
            records[gate_id].get("execution_scope") != "complete"
            or records[gate_id].get("status") != "passed"
        )
    )
    if missing or non_passing or incomplete_scope:
        raise EvidenceError(
            "release verdict is not green: "
            f"missing={missing}, non_passing={non_passing}, incomplete_scope={incomplete_scope}"
        )
    now = datetime.now(UTC)
    stale: list[str] = []
    future: list[str] = []
    for gate_id in required_gates:
        record = records[gate_id]
        if record["status"] != "passed":
            continue
        ended = datetime.fromisoformat(record["ended_at"].replace("Z", "+00:00"))
        age = (now - ended).total_seconds()
        if age < 0:
            future.append(gate_id)
        elif age > MAX_EVIDENCE_AGE_SECONDS:
            stale.append(gate_id)
    if stale or future:
        raise EvidenceError(
            f"release evidence timestamps invalid: stale={sorted(stale)}, future={sorted(future)}"
        )
    verify_artifacts(validated)
    profile_id = expected_profile or validated.get("qualification_profile")
    profile_gates = GATE_PROFILES.get(profile_id) if isinstance(profile_id, str) else None
    profile_complete = profile_gates is not None and frozenset(required_gates) == profile_gates
    verdict = {
        "schema": "ronin.release-verdict/v1",
        "commit": validated["commit"],
        "qualification_profile": profile_id,
        "qualification_scope": "complete-profile" if profile_complete else "custom-gate-set",
        "required_gates": sorted(required_gates),
        "status": "passed",
        "evidence": {
            gate_id: {
                "execution_scope": records[gate_id].get("execution_scope"),
                "command": records[gate_id]["command"],
                "environment": records[gate_id]["environment"],
                "started_at": records[gate_id]["started_at"],
                "ended_at": records[gate_id]["ended_at"],
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
    required.add_argument(
        "--required-gate",
        action="append",
        help="evaluate a custom gate set; this cannot establish a complete named profile",
    )
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
                expected_profile=args.profile if args.profile is not None else None,
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
