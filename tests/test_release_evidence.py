from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.release_evidence import (
    GATE_PROFILES,
    MERGE_REQUIRED_GATES,
    RELEASE_REQUIRED_GATES,
    SCHEMA,
    EvidenceError,
    load,
    merge,
    release_verdict,
    required_gates,
    validate_bundle,
)


def record(gate_id: str, status: str = "passed", commit: str = "abc123") -> dict[str, object]:
    value: dict[str, object] = {
        "gate_id": gate_id,
        "status": status,
        "commit": commit,
        "environment": {"fingerprint": "python-3.11/windows"},
        "command": "python -m pytest",
        "started_at": "2026-09-20T10:00:00Z",
        "ended_at": "2026-09-20T10:01:00Z",
    }
    if status == "passed":
        value["artifacts"] = ["logs/test.txt"]
        value["artifact_digests"] = {"logs/test.txt": "a" * 64}
    else:
        value["reason"] = "external service unavailable"
    return value


def test_validate_requires_identity_for_passed_gate() -> None:
    value = record("local-tests")
    del value["environment"]
    with pytest.raises(EvidenceError, match="missing required fields"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})


def test_validate_requires_exact_artifact_digests_for_passed_gate() -> None:
    value = record("local-tests")
    del value["artifact_digests"]
    with pytest.raises(EvidenceError, match="artifact_digests"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})

    value = record("local-tests")
    value["artifact_digests"] = {"logs/other.txt": "a" * 64}
    with pytest.raises(EvidenceError, match="missing artifact digests"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})

    value = record("local-tests")
    value["artifact_digests"]["logs/unrelated.txt"] = "a" * 64
    with pytest.raises(EvidenceError, match="undeclared artifacts"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})

    value = record("local-tests")
    value["artifacts"] = ["logs/test.txt", "logs/test.txt"]
    with pytest.raises(EvidenceError, match="duplicate artifacts"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})


def test_validate_requires_root_commit() -> None:
    with pytest.raises(EvidenceError, match="bundle commit is required"):
        validate_bundle({"schema": SCHEMA, "records": [record("unit")]})


def test_skipped_gate_requires_explicit_reason_and_is_not_pass() -> None:
    value = record("spark", "skipped")
    validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})
    del value["reason"]
    with pytest.raises(EvidenceError, match="requires reason"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})


def test_validate_rejects_malformed_or_reversed_timestamps() -> None:
    value = record("unit")
    value["started_at"] = "not-a-timestamp"
    with pytest.raises(EvidenceError, match="ISO-8601"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})
    value = record("unit")
    value["ended_at"] = "2026-09-20T09:59:00Z"
    with pytest.raises(EvidenceError, match="ended_at"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [value]})


def test_merge_is_deterministic_and_rejects_mixed_commits(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": [record("api")]}),
        encoding="utf-8",
    )
    result = merge([second, first])
    assert [item["gate_id"] for item in result["records"]] == ["api", "unit"]
    second.write_text(
        json.dumps(
            {"schema": SCHEMA, "commit": "other", "records": [record("api", commit="other")]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceError, match="one commit"):
        merge([first, second])


def test_load_rejects_duplicate_gate_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(
            {"schema": SCHEMA, "commit": "abc123", "records": [record("unit"), record("unit")]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceError, match="duplicate gate_id"):
        load(path)


def test_release_verdict_fails_closed_for_missing_or_skipped_gate() -> None:
    bundle = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}
    verdict = release_verdict(bundle, {"unit"})
    assert verdict["status"] == "passed"
    assert len(verdict["verdict_sha256"]) == 64
    assert verdict["evidence"]["unit"]["artifact_digests"]["logs/test.txt"] == "a" * 64
    with pytest.raises(EvidenceError, match="missing"):
        release_verdict(bundle, {"unit", "browser"})
    skipped = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit", "skipped")]}
    with pytest.raises(EvidenceError, match="non_passing"):
        release_verdict(skipped, {"unit"})


def test_release_verdict_rejects_empty_or_invalid_gate_sets() -> None:
    bundle = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}

    with pytest.raises(EvidenceError, match="non-empty set"):
        release_verdict(bundle, set())
    with pytest.raises(EvidenceError, match="non-empty set"):
        release_verdict(bundle, {" "})


def test_release_verdict_rejects_root_commit_drift() -> None:
    bundle = {"schema": SCHEMA, "commit": "other", "records": [record("unit")]}
    with pytest.raises(EvidenceError, match="does not match"):
        release_verdict(bundle, {"unit"})


def test_release_verdict_rejects_stale_expected_commit() -> None:
    bundle = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}
    with pytest.raises(EvidenceError, match="expected commit"):
        release_verdict(bundle, {"unit"}, expected_commit="current456")


def test_gate_profiles_keep_release_strictly_broader_than_merge() -> None:
    assert GATE_PROFILES["merge_required"] == MERGE_REQUIRED_GATES
    assert GATE_PROFILES["release_required"] == RELEASE_REQUIRED_GATES
    assert MERGE_REQUIRED_GATES < RELEASE_REQUIRED_GATES
    assert "mutation" in RELEASE_REQUIRED_GATES
    assert "installed-artifact" in RELEASE_REQUIRED_GATES


def test_unknown_gate_profile_fails_closed() -> None:
    with pytest.raises(EvidenceError, match="unknown gate profile"):
        required_gates("not-a-profile")


def test_cli_profile_verdict_uses_named_gate_set(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    records = [record(gate) for gate in sorted(MERGE_REQUIRED_GATES)]
    path.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": records}),
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.release_evidence",
            "verdict",
            str(path),
            "--profile",
            "merge_required",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert '"status": "passed"' in result.stdout


def test_aggregate_release_evidence_requires_exact_commit(tmp_path: Path) -> None:
    bundle = {"schema": SCHEMA, "commit": "abc123", "records": []}
    path = tmp_path / "empty.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.aggregate_release_evidence",
            str(path),
            "--output",
            str(tmp_path / "merged.json"),
            "--verdict-output",
            str(tmp_path / "verdict.json"),
            "--expected-commit",
            "abc123",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "records must be a non-empty array" in result.stdout


def test_emit_release_evidence_hashes_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "evidence.txt"
    artifact.write_text("qualified\n", encoding="utf-8")
    output = tmp_path / "bundle.json"
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "tools.emit_release_evidence",
            "--gate-id",
            "browser",
            "--commit",
            "abc123",
            "--status",
            "passed",
            "--fingerprint",
            "local-browser",
            "--command",
            "pytest browser",
            "--artifact",
            str(artifact),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    bundle = json.loads(output.read_text(encoding="utf-8"))
    assert len(bundle["records"]) == 1
    assert len(bundle["records"][0]["artifact_digests"][str(artifact)]) == 64
