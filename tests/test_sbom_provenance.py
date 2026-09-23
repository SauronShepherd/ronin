from __future__ import annotations

import hashlib
import json

import pytest

from tools.generate_sbom import build_evidence, verify_evidence


def test_sbom_evidence_binds_artifact_digest_and_can_be_verified(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    evidence = build_evidence(tmp_path, [artifact])
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    verify_evidence(output)
    assert evidence["schema"] == "ronin.sbom-provenance/v1"
    assert evidence["artifacts"][0]["sha256"]
    assert len(evidence["evidence_sha256"]) == 64


def test_sbom_verification_rejects_mutated_artifact(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(build_evidence(tmp_path, [artifact])), encoding="utf-8")
    artifact.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="artifact digest mismatch"):
        verify_evidence(output)


def test_sbom_verification_rejects_mutated_evidence(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    output = tmp_path / "evidence.json"
    value = build_evidence(tmp_path, [artifact])
    value["source"]["revision"] = "wrong"
    output.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence_sha256"):
        verify_evidence(output)


def test_sbom_verification_rejects_size_drift_even_when_digest_field_is_reused(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    value = build_evidence(tmp_path, [artifact])
    value["artifacts"][0]["bytes"] += 1
    value.pop("evidence_sha256")
    value["evidence_sha256"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        verify_evidence(output)
