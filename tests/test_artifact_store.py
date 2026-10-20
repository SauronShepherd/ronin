from __future__ import annotations

from pathlib import Path

import pytest
from studio_storage import (
    REQUIRED_ARTIFACT_REFERENCE_SOURCES,
    ArtifactIntegrityError,
    ArtifactRef,
    LocalArtifactStore,
    collect_unreferenced,
    plan_unreferenced,
)


def test_artifact_round_trip_is_content_addressed(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    first = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    second = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    assert first.digest == second.digest
    assert first.storage_ref == second.storage_ref
    assert store.get_bytes(first) == b"hello"
    assert store.verify(first)
    assert store.list_digests() == (first.digest,)
    assert store.storage_ref_for_digest(first.digest) == first.storage_ref
    assert store.delete(first)
    assert not store.delete(first)
    assert store.list_digests() == ()


def test_corrupted_artifact_fails_closed_and_same_content_repairs_it(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = LocalArtifactStore(root)
    ref = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    target = root / "sha256" / ref.digest[:2] / ref.digest
    target.write_bytes(b"tampered")
    assert not store.verify(ref)
    with pytest.raises(ArtifactIntegrityError, match="digest"):
        store.get_bytes(ref)

    repaired = store.put_bytes(role="stdout", data=b"hello", media_type="text/plain")
    assert repaired == ref
    assert store.verify(repaired)
    assert store.get_bytes(repaired) == b"hello"


def test_artifact_can_be_read_from_an_authorized_storage_reference(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    ref = store.put_bytes(role="stdout", data=b"portable payload", media_type="text/plain")

    assert store.get_bytes_by_storage_ref(ref.storage_ref, digest=ref.digest) == b"portable payload"
    with pytest.raises(ValueError, match="does not match"):
        store.get_bytes_by_storage_ref("artifact://sha256/" + "0" * 64, digest=ref.digest)
    (tmp_path / "artifacts" / "sha256" / ref.digest[:2] / ref.digest).write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError):
        store.get_bytes_by_storage_ref(ref.storage_ref, digest=ref.digest)


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


def test_retention_deletes_only_unreferenced_digests(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    live = store.put_bytes(role="live", data=b"live")
    stale = store.put_bytes(role="stale", data=b"stale")

    assert collect_unreferenced(store, (live.digest,)) == (stale.digest,)
    assert store.verify(live)
    assert not store.verify(stale)


def test_retention_plan_requires_all_reference_sources_and_never_deletes(
    tmp_path: Path,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    live = store.put_bytes(role="live", data=b"live")
    stale = store.put_bytes(role="stale", data=b"stale")

    incomplete = plan_unreferenced(store, {"ml_runs": (live.digest,)})
    assert not incomplete.complete
    assert incomplete.missing_sources == tuple(
        sorted(REQUIRED_ARTIFACT_REFERENCE_SOURCES - {"ml_runs"})
    )
    assert incomplete.candidate_digests == ()

    complete_snapshot = dict.fromkeys(REQUIRED_ARTIFACT_REFERENCE_SOURCES, ())
    complete_snapshot["ml_runs"] = (live.digest,)
    preview = plan_unreferenced(store, complete_snapshot)
    assert preview.complete
    assert preview.candidate_digests == (stale.digest,)
    assert store.verify(live)
    assert store.verify(stale)


def test_retention_plan_fails_closed_for_truncated_inventory(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.put_bytes(role="one", data=b"one")
    store.put_bytes(role="two", data=b"two")
    complete_snapshot = dict.fromkeys(REQUIRED_ARTIFACT_REFERENCE_SOURCES, ())

    preview = plan_unreferenced(store, complete_snapshot, page_size=1, max_objects=1)

    assert not preview.complete
    assert preview.inventory_truncated
    assert preview.candidate_digests == ()


def test_retention_plan_rejects_unknown_sources_and_invalid_digests(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="unknown artifact reference sources"):
        plan_unreferenced(store, {"unknown": ()})

    invalid = dict.fromkeys(REQUIRED_ARTIFACT_REFERENCE_SOURCES, ())
    invalid["ml_runs"] = ("not-a-digest",)
    with pytest.raises(ValueError, match="lowercase sha256"):
        plan_unreferenced(store, invalid)
