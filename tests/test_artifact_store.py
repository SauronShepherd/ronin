from __future__ import annotations

from pathlib import Path

import pytest
from studio_storage import ArtifactIntegrityError, ArtifactRef, LocalArtifactStore


def test_artifact_round_trip_is_content_addressed(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    first = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    second = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    assert first.digest == second.digest
    assert first.storage_ref == second.storage_ref
    assert store.get_bytes(first) == b"hello"
    assert store.verify(first)


def test_corrupted_artifact_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root)
    ref = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    target = root / "sha256" / ref.digest[:2] / ref.digest
    target.write_bytes(b"tampered")
    assert not store.verify(ref)
    with pytest.raises(ArtifactIntegrityError, match="digest"):
        store.get_bytes(ref)


def test_invalid_reference_cannot_escape_store(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    ref = ArtifactRef(
        role="stdout",
        digest_algorithm="sha256",
        digest="../etc/passwd",
        media_type="text/plain",
        size_bytes=0,
        storage_ref="artifact://sha256/../etc/passwd",
    )
    with pytest.raises(ValueError, match="digest"):
        store.get_bytes(ref)


def test_invalid_role_is_rejected_without_persisting(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="role"):
        store.put_bytes(role=" bad", data=b"secret")
