from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
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
    now = datetime.now(UTC)
    value: dict[str, object] = {
        "gate_id": gate_id,
        "status": status,
        "execution_scope": "complete",
        "commit": commit,
        "environment": {"fingerprint": "python-3.11/windows"},
        "command": "python -m pytest",
        "started_at": (now - timedelta(seconds=1)).isoformat(),
        "ended_at": now.isoformat(),
    }
    if status in {"passed", "failed"}:
        artifact = (
            Path(tempfile.gettempdir()) / "ronin-release-evidence-tests" / commit / f"{gate_id}.txt"
        )
        artifact.parent.mkdir(parents=True, exist_ok=True)
        content = f"{commit}:{gate_id}\n".encode()
        artifact.write_bytes(content)
        artifact_name = str(artifact.resolve())
        value["artifacts"] = [artifact_name]
        value["artifact_digests"] = {artifact_name: hashlib.sha256(content).hexdigest()}
    else:
        value["reason"] = "external service unavailable"
    return value


def _emitter_time_args() -> list[str]:
    ended = datetime.now(UTC)
    started = ended - timedelta(seconds=1)
    return ["--started-at", started.isoformat(), "--ended-at", ended.isoformat()]


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
    assert verdict["qualification_scope"] == "custom-gate-set"
    assert len(verdict["verdict_sha256"]) == 64
    assert verdict["evidence"]["unit"]["execution_scope"] == "complete"
    assert verdict["evidence"]["unit"]["command"] == "python -m pytest"
    assert verdict["evidence"]["unit"]["environment"]["fingerprint"] == "python-3.11/windows"
    artifact_name = verdict["evidence"]["unit"]["artifacts"][0]
    assert len(verdict["evidence"]["unit"]["artifact_digests"][artifact_name]) == 64
    with pytest.raises(EvidenceError, match="missing"):
        release_verdict(bundle, {"unit", "browser"})
    skipped = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit", "skipped")]}
    with pytest.raises(EvidenceError, match="non_passing"):
        release_verdict(skipped, {"unit"})


def test_release_verdict_rejects_diagnostic_or_unscoped_passed_gate() -> None:
    diagnostic_record = record("unit")
    diagnostic_record["execution_scope"] = "diagnostic"
    diagnostic = {"schema": SCHEMA, "commit": "abc123", "records": [diagnostic_record]}
    with pytest.raises(EvidenceError, match="incomplete_scope"):
        release_verdict(diagnostic, {"unit"})

    legacy_record = record("unit")
    legacy_record.pop("execution_scope")
    legacy = {"schema": SCHEMA, "commit": "abc123", "records": [legacy_record]}
    with pytest.raises(EvidenceError, match="incomplete_scope"):
        release_verdict(legacy, {"unit"})


def test_release_evidence_rejects_unknown_execution_scope() -> None:
    invalid_record = record("unit")
    invalid_record["execution_scope"] = "mostly-complete"

    with pytest.raises(EvidenceError, match="unsupported execution_scope"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [invalid_record]})


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


def test_release_verdict_rehashes_artifacts_without_named_profile() -> None:
    unit_record = record("unit")
    artifact_path = Path(unit_record["artifacts"][0])
    artifact_path.write_text("tampered after receipt\n", encoding="utf-8")
    bundle = {"schema": SCHEMA, "commit": "abc123", "records": [unit_record]}

    with pytest.raises(EvidenceError, match="digest mismatch"):
        release_verdict(bundle, {"unit"})


def test_release_verdict_rejects_stale_expected_commit() -> None:
    bundle = {"schema": SCHEMA, "commit": "abc123", "records": [record("unit")]}
    with pytest.raises(EvidenceError, match="expected commit"):
        release_verdict(bundle, {"unit"}, expected_commit="current456")


def test_release_verdict_labels_profile_subset_as_custom_gate_set() -> None:
    bundle = {
        "schema": SCHEMA,
        "commit": "abc123",
        "qualification_profile": "release_required",
        "records": [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)],
    }

    verdict = release_verdict(bundle, {"browser"})

    assert verdict["status"] == "passed"
    assert verdict["qualification_profile"] == "release_required"
    assert verdict["qualification_scope"] == "custom-gate-set"


def test_gate_profiles_keep_release_strictly_broader_than_merge() -> None:
    assert GATE_PROFILES["merge_required"] == MERGE_REQUIRED_GATES
    assert GATE_PROFILES["release_required"] == RELEASE_REQUIRED_GATES
    assert MERGE_REQUIRED_GATES < RELEASE_REQUIRED_GATES
    assert "mutation" not in RELEASE_REQUIRED_GATES
    assert "installed-artifact" in RELEASE_REQUIRED_GATES


def test_unknown_gate_profile_fails_closed() -> None:
    with pytest.raises(EvidenceError, match="unknown gate profile"):
        required_gates("not-a-profile")


def test_release_profile_rejects_wrong_profile_and_gate_set() -> None:
    bundle = {
        "schema": SCHEMA,
        "commit": "abc123",
        "qualification_profile": "local_mvp_required",
        "records": [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)],
    }
    with pytest.raises(EvidenceError, match="does not match expected profile"):
        release_verdict(
            bundle,
            set(RELEASE_REQUIRED_GATES),
            expected_profile="release_required",
        )
    bundle["qualification_profile"] = "release_required"
    with pytest.raises(EvidenceError, match="required gates do not match"):
        release_verdict(bundle, {"local-quality"}, expected_profile="release_required")


def test_release_profile_rejects_stale_or_future_evidence() -> None:
    stale_records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    stale_end = datetime.now(UTC) - timedelta(hours=25)
    stale_records[0]["started_at"] = (stale_end - timedelta(seconds=1)).isoformat()
    stale_records[0]["ended_at"] = stale_end.isoformat()
    stale = {
        "schema": SCHEMA,
        "commit": "abc123",
        "qualification_profile": "release_required",
        "records": stale_records,
    }
    with pytest.raises(EvidenceError, match="stale"):
        release_verdict(stale, set(RELEASE_REQUIRED_GATES), expected_profile="release_required")

    future_records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    future_records[0]["ended_at"] = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    future = {
        "schema": SCHEMA,
        "commit": "abc123",
        "qualification_profile": "release_required",
        "records": future_records,
    }
    with pytest.raises(EvidenceError, match="future"):
        release_verdict(future, set(RELEASE_REQUIRED_GATES), expected_profile="release_required")


@pytest.mark.parametrize("artifact_state", ["missing", "modified"])
def test_release_profile_rejects_missing_or_modified_archived_artifacts(
    artifact_state: str,
) -> None:
    records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    artifact_path = Path(records[0]["artifacts"][0])
    if artifact_state == "missing":
        artifact_path.unlink()
    else:
        artifact_path.write_text("changed after qualification", encoding="utf-8")
    bundle = {
        "schema": SCHEMA,
        "commit": "abc123",
        "qualification_profile": "release_required",
        "records": records,
    }
    expected = "missing" if artifact_state == "missing" else "digest mismatch"
    with pytest.raises(EvidenceError, match=expected):
        release_verdict(bundle, set(RELEASE_REQUIRED_GATES), expected_profile="release_required")


def test_failed_gate_requires_archived_logs_and_digests() -> None:
    failed = record("local-quality", status="failed")
    del failed["artifacts"]
    with pytest.raises(EvidenceError, match="failed evidence requires artifacts"):
        validate_bundle({"schema": SCHEMA, "commit": "abc123", "records": [failed]})


def test_cli_profile_verdict_uses_named_gate_set(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    records = [record(gate) for gate in sorted(MERGE_REQUIRED_GATES)]
    path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "commit": "abc123",
                "qualification_profile": "merge_required",
                "records": records,
            }
        ),
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
        json.dumps(
            {
                "schema": SCHEMA,
                "commit": "abc123",
                "qualification_profile": "release_required",
                "records": records,
            }
        ),
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
    assert merged["qualification_profile"] == "release_required"
    assert verdict["status"] == "passed"
    assert verdict["qualification_scope"] == "complete-profile"
    assert verdict["required_gates"] == sorted(RELEASE_REQUIRED_GATES)
    assert '"status": "passed"' in capsys.readouterr().out


def test_aggregate_release_evidence_cli_rejects_diagnostic_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    browser_record = next(item for item in records if item["gate_id"] == "browser")
    browser_record["execution_scope"] = "diagnostic"
    path = tmp_path / "diagnostic-release.json"
    path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "commit": "abc123",
                "qualification_profile": "release_required",
                "records": records,
            }
        ),
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
            "abc123",
        ],
    )

    assert aggregate_release_evidence_main() == 2
    assert "incomplete_scope=['browser']" in capsys.readouterr().out


def test_aggregate_release_evidence_cli_rejects_mismatched_expected_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "release.json"
    records = [record(gate) for gate in sorted(RELEASE_REQUIRED_GATES)]
    path.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "commit": "abc123",
                "qualification_profile": "release_required",
                "records": records,
            }
        ),
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
            "--execution-scope",
            "complete",
            "--fingerprint",
            "local-browser",
            "--command",
            "pytest browser",
            *_emitter_time_args(),
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
        execution_scope="complete",
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
        execution_scope="diagnostic",
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
            "--execution-scope",
            "complete",
            "--fingerprint",
            "local",
            "--command",
            "pytest",
            *_emitter_time_args(),
            "--profile",
            "release_required",
            "--artifact",
            str(artifact),
            "--output",
            str(output),
        ],
    )
    assert emit_release_evidence.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["records"][0]["status"] == "passed"
    assert '"status": "passed"' in capsys.readouterr().out
