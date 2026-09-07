from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from studio_kernel import (
    CellExecutionRequest,
    ExecutionAttemptId,
    ExecutionEvidenceReference,
    KernelDirective,
)
from studio_notebook import CellId
from studio_orchestrator import RunId, StoredEvidenceRef
from studio_runners import LocalExecutionEvidenceStore
from studio_storage import ArtifactIntegrityError, LocalArtifactStore


def _cell() -> CellExecutionRequest:
    return CellExecutionRequest(
        CellId("cell-1"),
        "print('authored')",
        "print('executed')",
        "python",
        (),
        KernelDirective("test", "source.execute"),
    )


def test_execution_evidence_identity_excludes_physical_locator() -> None:
    digest = "a" * 64
    first = ExecutionEvidenceReference(
        "log",
        "local-evidence://first/log.json",
        "sha256",
        digest,
        "application/json",
        17,
    )
    moved = ExecutionEvidenceReference(
        "log",
        "artifact://sha256/" + digest,
        "sha256",
        digest,
        "application/json",
        17,
    )

    assert first.portable_identity == moved.portable_identity
    assert first.portable_payload() == {
        "version": 1,
        "role": "log",
        "digest_algorithm": "sha256",
        "digest": digest,
        "media_type": "application/json",
        "size_bytes": 17,
        "locator": "local-evidence://first/log.json",
        "availability": "available",
    }


def test_execution_evidence_portable_metadata_fails_closed() -> None:
    opaque = ExecutionEvidenceReference("log", "memory://log")
    assert opaque.portable_identity is None
    with pytest.raises(ValueError, match="portable content identity"):
        opaque.portable_payload()
    with pytest.raises(ValueError, match="requires algorithm"):
        ExecutionEvidenceReference("log", "memory://log", digest="a" * 64)
    with pytest.raises(ValueError, match="unsupported evidence digest"):
        ExecutionEvidenceReference("log", "memory://log", "md5", "a" * 64, None, 1)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        ExecutionEvidenceReference("log", "memory://log", "sha256", "A" * 64, None, 1)
    with pytest.raises(ValueError, match="non-negative"):
        ExecutionEvidenceReference("log", "memory://log", "sha256", "a" * 64, None, -1)
    with pytest.raises(ValueError, match="media type"):
        ExecutionEvidenceReference("log", "memory://log", "sha256", "a" * 64, " bad", 1)


def test_durable_evidence_mapping_is_lossless_and_rejects_unavailable_refs() -> None:
    reference = ExecutionEvidenceReference(
        "resource",
        "local-evidence://attempt/cell/resource.json",
        "sha256",
        "b" * 64,
        "application/json",
        23,
    )
    stored = StoredEvidenceRef.from_execution_reference(
        run_id=RunId("00000000-0000-0000-0000-000000000001"),
        cell_id="cell-1",
        reference=reference,
    )

    assert stored.portable_identity == (
        "resource",
        "sha256",
        "b" * 64,
        "application/json",
        23,
    )
    assert stored.to_execution_reference() == reference

    with pytest.raises(ValueError, match="portable content identity"):
        StoredEvidenceRef.from_execution_reference(
            run_id=stored.run_id,
            cell_id="cell-1",
            reference=ExecutionEvidenceReference("log", "memory://log"),
        )
    with pytest.raises(ValueError, match="not a kernel execution evidence kind"):
        StoredEvidenceRef(
            stored.run_id,
            "cell-1",
            "cell-result",
            "sha256",
            "c" * 64,
            "application/json",
            1,
            "artifact://sha256/" + "c" * 64,
        ).to_execution_reference()
    with pytest.raises(ValueError, match="unavailable"):
        StoredEvidenceRef(
            stored.run_id,
            "cell-1",
            "log",
            "sha256",
            "c" * 64,
            "application/json",
            None,
            None,
        ).to_execution_reference()


def test_local_execution_and_artifact_adapters_share_content_identity(tmp_path: Path) -> None:
    payload = {"z": 1, "a": "value"}
    execution_store = LocalExecutionEvidenceStore(tmp_path / "execution")
    reference = execution_store.persist_json(
        "resource",
        ExecutionAttemptId("attempt-1"),
        _cell(),
        payload,
    )
    canonical = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    artifact_store = LocalArtifactStore(tmp_path / "artifacts")
    artifact = artifact_store.put_bytes(
        role="resource",
        data=canonical,
        media_type="application/vnd.ronin.execution-evidence+json",
    )

    assert reference.digest_algorithm == artifact.digest_algorithm == "sha256"
    assert reference.digest == artifact.digest == hashlib.sha256(canonical).hexdigest()
    assert reference.size_bytes == artifact.size_bytes == len(canonical)
    assert reference.media_type == artifact.media_type
    assert reference.ref.startswith("local-evidence://")
    assert artifact.storage_ref.startswith("artifact://sha256/")

    artifact_path = (
        tmp_path
        / "artifacts"
        / "sha256"
        / artifact.digest[:2]
        / artifact.digest
    )
    artifact_path.write_bytes(b"corrupt")
    assert artifact_store.verify(artifact) is False
    with pytest.raises(ArtifactIntegrityError, match="digest verification"):
        artifact_store.get_bytes(artifact)
