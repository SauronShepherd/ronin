from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from studio_storage import (
    BUNDLE_MANIFEST_PATH,
    BundleFile,
    BundleIntegrityError,
    extract_bundle,
    verify_bundle,
    write_bundle,
)


def _files() -> tuple[BundleFile, ...]:
    return (
        BundleFile("project/notebook.py", "text/x-python", b"print('hello')\n"),
        BundleFile("metadata/project.json", "application/json", b'{"name":"demo"}'),
    )


def test_bundle_bytes_are_deterministic_and_round_trip(tmp_path: Path) -> None:
    first = tmp_path / "first.roninbundle"
    second = tmp_path / "second.roninbundle"
    first_manifest = write_bundle(first, _files())
    second_manifest = write_bundle(second, reversed(_files()))

    assert first.read_bytes() == second.read_bytes()
    assert first_manifest == second_manifest
    assert verify_bundle(first) == first_manifest

    extracted = tmp_path / "extracted"
    manifest = extract_bundle(first, extracted)
    assert manifest == first_manifest
    assert (extracted / "project/notebook.py").read_bytes() == b"print('hello')\n"
    assert (extracted / "metadata/project.json").read_bytes() == b'{"name":"demo"}'


def test_bundle_rejects_duplicate_payload_paths() -> None:
    with pytest.raises(ValueError, match="paths must be unique"):
        write_bundle(
            Path("ignored.roninbundle"),
            (
                BundleFile("same.txt", "text/plain", b"one"),
                BundleFile("same.txt", "text/plain", b"two"),
            ),
        )


def test_bundle_rejects_reserved_manifest_payload_path() -> None:
    with pytest.raises(ValueError, match="reserved"):
        BundleFile(BUNDLE_MANIFEST_PATH, "application/json", b"{}")


def test_bundle_detects_payload_tampering(tmp_path: Path) -> None:
    original = tmp_path / "bundle.roninbundle"
    write_bundle(original, _files())

    tampered = tmp_path / "tampered.roninbundle"
    with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "project/notebook.py":
                data = b"print('tampered')\n"
            target.writestr(info, data)

    with pytest.raises(BundleIntegrityError, match="digest"):
        verify_bundle(tampered)


def test_bundle_rejects_unmanifested_member(tmp_path: Path) -> None:
    path = tmp_path / "bundle.roninbundle"
    write_bundle(path, _files())
    with zipfile.ZipFile(path, mode="a") as archive:
        archive.writestr("unexpected.txt", b"not in manifest")

    with pytest.raises(BundleIntegrityError, match="exactly match"):
        verify_bundle(path)


def test_bundle_rejects_path_traversal_member_before_extraction(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.roninbundle"
    with zipfile.ZipFile(path, mode="w") as archive:
        archive.writestr(BUNDLE_MANIFEST_PATH, '{"schema_version":1,"entries":[],"migration_reports":[]}')
        archive.writestr("../escape.txt", b"escape")

    with pytest.raises(BundleIntegrityError, match="unsafe components"):
        verify_bundle(path)
    assert not (tmp_path / "escape.txt").exists()


def test_extract_requires_new_target_directory(tmp_path: Path) -> None:
    path = tmp_path / "bundle.roninbundle"
    write_bundle(path, _files())
    target = tmp_path / "existing"
    target.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        extract_bundle(path, target)
