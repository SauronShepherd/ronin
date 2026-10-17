from __future__ import annotations

import hashlib
import json

import pytest

from tools import generate_sbom
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


def test_sbom_verification_rejects_wrong_candidate_revision(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    evidence = build_evidence(tmp_path, [artifact])
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match expected revision"):
        verify_evidence(output, expected_revision="wrong-candidate")


def test_sbom_verification_rejects_unknown_source_revision(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    evidence = build_evidence(tmp_path, [artifact])
    evidence["source"]["revision"] = "unknown"
    evidence.pop("evidence_sha256")
    evidence["evidence_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match expected revision"):
        verify_evidence(output, expected_revision="candidate")


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


def test_sbom_verification_rejects_unknown_schema_even_with_valid_digest(tmp_path):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    value = build_evidence(tmp_path, [artifact])
    value["schema"] = "foreign.schema/v1"
    value.pop("evidence_sha256")
    value["evidence_sha256"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported SBOM/provenance evidence schema"):
        verify_evidence(output)


def test_sbom_build_rejects_missing_and_duplicate_artifacts(tmp_path):
    with pytest.raises(ValueError, match="all artifacts must exist"):
        build_evidence(tmp_path, [])
    missing = tmp_path / "missing.whl"
    with pytest.raises(ValueError, match="all artifacts must exist"):
        build_evidence(tmp_path, [missing])
    first = tmp_path / "one" / "same.whl"
    second = tmp_path / "two" / "same.whl"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    with pytest.raises(ValueError, match="names must be unique"):
        build_evidence(tmp_path, [first, second])


def test_sbom_revision_falls_back_to_unknown_on_git_error(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise generate_sbom.subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(generate_sbom.subprocess, "check_output", fail)
    assert generate_sbom._git_revision(tmp_path) == "unknown"
    monkeypatch.setattr(generate_sbom.subprocess, "check_output", lambda *_args, **_kwargs: "abc\n")
    assert generate_sbom._git_revision(tmp_path) == "abc"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(artifacts=[]), "must contain artifacts"),
        (lambda value: value.update(artifacts=[None]), "record must be an object"),
        (
            lambda value: value.update(artifacts=[{"path": "", "sha256": "bad", "bytes": -1}]),
            "invalid path, digest, or size",
        ),
        (
            lambda value: value.update(
                artifacts=[{"path": "missing", "sha256": "a" * 64, "bytes": 0}]
            ),
            "digest mismatch",
        ),
        (lambda value: value.update(source={"revision": " "}), "revision is missing"),
    ],
)
def test_sbom_verification_rejects_malformed_evidence(tmp_path, mutation, message):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    value = build_evidence(tmp_path, [artifact])
    mutation(value)
    value.pop("evidence_sha256")
    value["evidence_sha256"] = hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output = tmp_path / "evidence.json"
    output.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        verify_evidence(output)


def test_sbom_cli_generates_and_verifies_evidence(tmp_path, monkeypatch):
    artifact = tmp_path / "ronin.whl"
    artifact.write_bytes(b"candidate")
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(
        "sys.argv",
        ["generate-sbom", "--root", str(tmp_path), "--output", str(output), str(artifact)],
    )
    assert generate_sbom.main() == 0
    monkeypatch.setattr(
        "sys.argv", ["generate-sbom", "--verify", "--output", str(output), str(artifact)]
    )
    assert generate_sbom.main() == 0


def test_sbom_verification_rejects_non_object_json(tmp_path):
    output = tmp_path / "evidence.json"
    output.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        verify_evidence(output)
