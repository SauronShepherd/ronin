from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools import emit_release_evidence, release_evidence
from tools.aggregate_release_evidence import main as aggregate_release_evidence_main
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

    value = record("local-tests")
    value["artifact_digests"] = {None: "a" * 64}  # type: ignore[dict-item]
    with pytest.raises(EvidenceError, match="invalid name"):
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
    assert "mutation" not in RELEASE_REQUIRED_GATES
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


def test_aggregate_release_evidence_cli_writes_exact_candidate_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "release.json"
    records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    path.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": records}),
        encoding="utf-8",
    )
    merged_path = tmp_path / "merged.json"
    verdict_path = tmp_path / "verdict.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aggregate-release-evidence",
            str(path),
            "--output",
            str(merged_path),
            "--verdict-output",
            str(verdict_path),
            "--expected-commit",
            "abc123",
        ],
    )

    assert aggregate_release_evidence_main() == 0

    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    assert merged["commit"] == "abc123"
    assert verdict["status"] == "passed"
    assert verdict["required_gates"] == sorted(RELEASE_REQUIRED_GATES)
    assert '"status": "passed"' in capsys.readouterr().out


def test_aggregate_release_evidence_cli_rejects_mismatched_expected_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "release.json"
    records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    path.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": records}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "aggregate-release-evidence",
            str(path),
            "--output",
            str(tmp_path / "merged.json"),
            "--verdict-output",
            str(tmp_path / "verdict.json"),
            "--expected-commit",
            "other-commit",
        ],
    )

    assert aggregate_release_evidence_main() == 2
    assert "does not match expected commit" in capsys.readouterr().out


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


def test_release_evidence_cli_validates_merges_and_verifies_exact_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps({"schema": SCHEMA, "commit": "abc123", "records": [record("api")]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["release-evidence", "validate", str(first)])
    assert release_evidence._main() == 0
    assert '"commit": "abc123"' in capsys.readouterr().out

    merged = tmp_path / "merged.json"
    monkeypatch.setattr(
        sys, "argv", ["release-evidence", "merge", str(merged), str(second), str(first)]
    )
    assert release_evidence._main() == 0
    assert [item["gate_id"] for item in json.loads(merged.read_text())["records"]] == [
        "api",
        "unit",
    ]
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release-evidence",
            "verdict",
            str(first),
            "--required-gate",
            "unit",
            "--expected-commit",
            "abc123",
        ],
    )
    assert release_evidence._main() == 0
    assert '"status": "passed"' in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release-evidence",
            "verdict",
            str(first),
            "--required-gate",
            "unit",
            "--expected-commit",
            "stale",
        ],
    )
    assert release_evidence._main() == 2
    assert "release evidence invalid" in capsys.readouterr().out


def test_release_evidence_rejects_invalid_input_shapes_and_merge_duplicates(tmp_path: Path) -> None:
    invalid = record("unit")
    invalid["environment"] = []
    with pytest.raises(EvidenceError, match="environment must be an object"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [invalid]})

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    duplicate = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}
    first.write_text(json.dumps(duplicate), encoding="utf-8")
    second.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(EvidenceError, match="duplicate gate_id across bundles"):
        merge([first, second])

    unreadable = tmp_path / "unreadable.json"
    unreadable.write_text("{", encoding="utf-8")
    with pytest.raises(EvidenceError, match="cannot read evidence bundle"):
        load(unreadable)


def test_release_evidence_emitter_direct_api_and_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("release evidence", encoding="utf-8")
    passed = emit_release_evidence.build_record(
        gate_id="unit",
        commit="abc123",
        status="passed",
        fingerprint="local",
        command="pytest",
        artifacts=[artifact],
        reason=None,
    )
    assert passed["artifact_digests"][str(artifact)]
    skipped = emit_release_evidence.build_record(
        gate_id="optional",
        commit="abc123",
        status="skipped",
        fingerprint="local",
        command="pytest optional",
        artifacts=[],
        reason="not configured",
    )
    assert skipped["reason"] == "not configured"

    output = tmp_path / "emitted.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "emit-release-evidence",
            "--gate-id",
            "unit",
            "--commit",
            "abc123",
            "--status",
            "passed",
            "--fingerprint",
            "local",
            "--command",
            "pytest",
            "--artifact",
            str(artifact),
            "--output",
            str(output),
        ],
    )
    assert emit_release_evidence.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["records"][0]["status"] == "passed"
    assert '"status": "passed"' in capsys.readouterr().out
