from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.release_evidence import (
    SCHEMA,
    EvidenceError,
    load,
    merge,
    release_verdict,
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


def test_release_verdict_rejects_root_commit_drift() -> None:
    bundle = {"schema": SCHEMA, "commit": "other", "records": [record("unit")]}
    with pytest.raises(EvidenceError, match="does not match"):
        release_verdict(bundle, {"unit"})
