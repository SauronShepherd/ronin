from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.release_evidence import EvidenceError, SCHEMA, load, merge, validate_bundle


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
    else:
        value["reason"] = "external service unavailable"
    return value


def test_validate_requires_identity_for_passed_gate() -> None:
    value = record("local-tests")
    del value["environment"]
    with pytest.raises(EvidenceError, match="missing required fields"):
        validate_bundle({"schema": SCHEMA, "records": [value]})


def test_skipped_gate_requires_explicit_reason_and_is_not_pass() -> None:
    value = record("spark", "skipped")
    validate_bundle({"schema": SCHEMA, "records": [value]})
    del value["reason"]
    with pytest.raises(EvidenceError, match="requires reason"):
        validate_bundle({"schema": SCHEMA, "records": [value]})


def test_merge_is_deterministic_and_rejects_mixed_commits(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text(json.dumps({"schema": SCHEMA, "records": [record("unit")] }), encoding="utf-8")
    second.write_text(json.dumps({"schema": SCHEMA, "records": [record("api")] }), encoding="utf-8")
    result = merge([second, first])
    assert [item["gate_id"] for item in result["records"]] == ["api", "unit"]
    second.write_text(json.dumps({"schema": SCHEMA, "records": [record("api", commit="other")] }), encoding="utf-8")
    with pytest.raises(EvidenceError, match="one commit"):
        merge([first, second])


def test_load_rejects_duplicate_gate_ids(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps({"schema": SCHEMA, "records": [record("unit"), record("unit")] }), encoding="utf-8")
    with pytest.raises(EvidenceError, match="duplicate gate_id"):
        load(path)
