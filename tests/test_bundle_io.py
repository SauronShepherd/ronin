from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import studio_storage.bundle_payload as bundle_payload
from studio_storage import (
    BUNDLE_MANIFEST_PATH,
    BundleFile,
    BundleIntegrityError,
    extract_bundle,
    verify_bundle,
    write_bundle,
)
from studio_storage.bundle_payload import BundlePayloadReader, read_bundle_payload


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


def test_bundle_payload_rejects_invalid_read_request_before_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "bundle.roninbundle"
    write_bundle(path, _files())

    def verification_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid payload request must fail before archive verification")

    monkeypatch.setattr(bundle_payload, "_verify_payloads", verification_must_not_run)

    with pytest.raises(ValueError, match="max_bytes must be positive"):
        read_bundle_payload(path, "project/notebook.py", max_bytes=0)
    with pytest.raises(BundleIntegrityError, match="manifest is not a payload"):
        read_bundle_payload(path, BUNDLE_MANIFEST_PATH)


def test_bundle_payload_reader_enforces_state_and_entry_limits(tmp_path: Path) -> None:
    path = tmp_path / "bundle.roninbundle"
    manifest = write_bundle(path, _files())
    reader = BundlePayloadReader(path)

    with pytest.raises(RuntimeError, match="not open"):
        _ = reader.manifest
    with pytest.raises(RuntimeError, match="not open"):
        reader.read_payload("project/notebook.py")

    with reader as opened:
        assert opened.manifest == manifest
        with pytest.raises(RuntimeError, match="re-entered"):
            opened.__enter__()
        with pytest.raises(ValueError, match="max_bytes must be positive"):
            opened.read_payload("project/notebook.py", max_bytes=0)
        with pytest.raises(BundleIntegrityError, match="manifest is not a payload"):
            opened.read_payload(BUNDLE_MANIFEST_PATH)
        with pytest.raises(BundleIntegrityError, match="not declared"):
            opened.read_payload("missing.txt")
        with pytest.raises(BundleIntegrityError, match="in-memory read limit"):
            opened.read_payload("project/notebook.py", max_bytes=1)

    with pytest.raises(RuntimeError, match="not open"):
        reader.read_payload("project/notebook.py")
    with pytest.raises(RuntimeError, match="not open"):
        _ = reader.manifest
    reader.close()


def test_bundle_payload_reader_normalizes_archive_io_errors(tmp_path: Path) -> None:
    with (
        pytest.raises(BundleIntegrityError, match="archive is unreadable"),
        BundlePayloadReader(tmp_path / "missing.roninbundle"),
    ):
        pytest.fail("missing archive must not open")

    path = tmp_path / "bundle.roninbundle"
    write_bundle(path, _files())
    with BundlePayloadReader(path) as reader:
        assert reader._archive is not None

        def fail_open(*_args: object, **_kwargs: object) -> None:
            raise OSError("read failed")

        reader._archive.open = fail_open  # type: ignore[method-assign]
        with pytest.raises(BundleIntegrityError, match="archive is unreadable"):
            reader.read_payload("project/notebook.py")


def test_bundle_payload_reader_rechecks_bytes_after_archive_verification(tmp_path: Path) -> None:
    path = tmp_path / "bundle.roninbundle"
    write_bundle(path, _files())
    with BundlePayloadReader(path) as reader:
        assert reader._archive is not None
        reader._archive.open = lambda *_args, **_kwargs: BytesIO(b"x" * 64)  # type: ignore[method-assign]
        with pytest.raises(BundleIntegrityError, match="expanded beyond its declared limit"):
            reader.read_payload("project/notebook.py")

    with BundlePayloadReader(path) as reader:
        assert reader._archive is not None
        entry_bytes = b"x" * len(b"print('hello')\n")
        reader._archive.open = lambda *_args, **_kwargs: BytesIO(entry_bytes)  # type: ignore[method-assign]
        with pytest.raises(BundleIntegrityError, match="changed during verified read"):
            reader.read_payload("project/notebook.py")


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
    with (
        pytest.raises(BundleIntegrityError, match="digest"),
        BundlePayloadReader(tampered),
    ):
        pytest.fail("tampered archive must fail during reader verification")


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
        archive.writestr(
            BUNDLE_MANIFEST_PATH, '{"schema_version":1,"entries":[],"migration_reports":[]}'
        )
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
