from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from tools.bind_container_sbom import (
    ContainerSbomError,
    _archive_identity,
    _load_json,
    _one_property,
    _os_package_count,
    _property_values,
)


def _write_tar(path: Path, members: list[tuple[str, bytes, bool]]) -> None:
    with tarfile.open(path, mode="w") as archive:
        for name, payload, is_directory in members:
            member = tarfile.TarInfo(name)
            if is_directory:
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            else:
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "cannot read"),
        ("[]", "must be a JSON object"),
        ("{", "cannot read"),
    ],
)
def test_load_json_rejects_missing_malformed_and_non_object_documents(tmp_path, content, message):
    path = tmp_path / "evidence.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ContainerSbomError, match=message):
        _load_json(path, "test evidence")


@pytest.mark.parametrize(
    "component",
    [
        {"properties": None},
        {"properties": [None]},
        {"properties": [{"name": "x", "value": None}]},
    ],
)
def test_properties_reject_invalid_shapes(component):
    with pytest.raises(ContainerSbomError, match="invalid property|must be an array"):
        _property_values(component, "x")


@pytest.mark.parametrize(
    "properties",
    [
        [],
        [{"name": "ref", "value": ""}],
        [{"name": "ref", "value": "a"}, {"name": "ref", "value": "b"}],
    ],
)
def test_one_property_requires_one_nonempty_value(properties):
    with pytest.raises(ContainerSbomError, match="exactly one"):
        _one_property({"properties": properties}, "ref")


@pytest.mark.parametrize(
    "component",
    [
        {"type": "library", "purl": "pkg:apk/alpine/demo@1", "version": "1", "bom-ref": "r"},
        {"type": "library", "name": "demo", "purl": "pkg:apk/alpine/demo@1", "bom-ref": "r"},
        {"type": "library", "name": "demo", "version": "1", "purl": "pkg:apk/alpine/demo@1"},
    ],
)
def test_os_package_inventory_rejects_missing_component_identity(component):
    with pytest.raises(ContainerSbomError, match="invalid component"):
        _os_package_count([component])


def test_os_package_inventory_ignores_non_os_records_and_rejects_duplicate_refs():
    non_os = {"type": "application", "name": "trivy", "version": "0.76.1"}
    language = {
        "type": "library",
        "name": "go",
        "purl": "pkg:golang/go@1",
        "version": "1",
        "bom-ref": "go",
    }
    package = {
        "type": "library",
        "name": "musl",
        "purl": "pkg:apk/alpine/musl@1",
        "version": "1",
        "bom-ref": "musl",
    }
    assert _os_package_count([non_os, language, package]) == 1
    duplicate = {**package, "name": "busybox"}
    with pytest.raises(ContainerSbomError, match="invalid component"):
        _os_package_count([package, duplicate])


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ([], "exactly one manifest"),
        ([("manifest.json", b"{}", True)], "exactly one manifest"),
        ([("manifest.json", b"x" * (1024 * 1024 + 1), False)], "unexpectedly large"),
        ([("manifest.json", b"{", False)], "cannot inspect Docker image archive"),
        ([("manifest.json", b"{}", False)], "exactly one image entry"),
    ],
)
def test_archive_identity_rejects_invalid_manifest_inputs(tmp_path, members, message):
    path = tmp_path / "image.tar"
    _write_tar(path, members)
    with pytest.raises(ContainerSbomError, match=message):
        _archive_identity(path)


@pytest.mark.parametrize(
    ("config_path", "tags", "message"),
    [
        ("blobs/sha256/" + "a" * 64, [], "invalid config or tags"),
        ("blobs/sha256/" + "a" * 64, ["tag", "tag"], "invalid config or tags"),
        ("blobs/sha256/" + "a" * 64, [None], "invalid config or tags"),
        ("../config.json", ["tag"], "config path must be"),
        ("/blobs/sha256/" + "a" * 64, ["tag"], "config path must be"),
    ],
)
def test_archive_identity_rejects_bad_config_paths_and_tags(tmp_path, config_path, tags, message):
    manifest = json.dumps([{"Config": config_path, "RepoTags": tags, "Layers": []}]).encode()
    path = tmp_path / "image.tar"
    _write_tar(path, [("manifest.json", manifest, False)])
    with pytest.raises(ContainerSbomError, match=message):
        _archive_identity(path)


def test_archive_identity_rejects_missing_duplicate_large_and_non_file_config_blobs(tmp_path):
    config = b'{"architecture":"amd64"}'
    digest = hashlib.sha256(config).hexdigest()
    config_path = f"blobs/sha256/{digest}"
    manifest = json.dumps(
        [{"Config": config_path, "RepoTags": ["ronin:test"], "Layers": []}]
    ).encode()

    missing = tmp_path / "missing.tar"
    _write_tar(missing, [("manifest.json", manifest, False)])
    with pytest.raises(ContainerSbomError, match="exactly one config blob"):
        _archive_identity(missing)

    duplicate = tmp_path / "duplicate.tar"
    _write_tar(
        duplicate,
        [
            ("manifest.json", manifest, False),
            (config_path, config, False),
            (config_path, config, False),
        ],
    )
    with pytest.raises(ContainerSbomError, match="exactly one config blob"):
        _archive_identity(duplicate)

    directory = tmp_path / "directory.tar"
    _write_tar(directory, [("manifest.json", manifest, False), (config_path, b"", True)])
    with pytest.raises(ContainerSbomError, match="regular file"):
        _archive_identity(directory)

    large_config = b"x" * (1024 * 1024 + 1)
    large_digest = hashlib.sha256(large_config).hexdigest()
    large_path = f"blobs/sha256/{large_digest}"
    large_manifest = json.dumps(
        [{"Config": large_path, "RepoTags": ["ronin:test"], "Layers": []}]
    ).encode()
    large = tmp_path / "large-config.tar"
    _write_tar(large, [("manifest.json", large_manifest, False), (large_path, large_config, False)])
    with pytest.raises(ContainerSbomError, match="unexpectedly large"):
        _archive_identity(large)


def test_archive_identity_rejects_config_digest_mismatch_and_unreadable_member(
    tmp_path, monkeypatch
):
    config = b"correct config"
    digest = hashlib.sha256(config).hexdigest()
    config_path = f"blobs/sha256/{digest}"
    manifest = json.dumps(
        [{"Config": config_path, "RepoTags": ["ronin:test"], "Layers": []}]
    ).encode()
    path = tmp_path / "bad-digest.tar"
    _write_tar(path, [("manifest.json", manifest, False), (config_path, b"wrong", False)])
    with pytest.raises(ContainerSbomError, match="digest does not match"):
        _archive_identity(path)

    valid = tmp_path / "valid.tar"
    _write_tar(valid, [("manifest.json", manifest, False), (config_path, config, False)])
    extractfile = tarfile.TarFile.extractfile

    def unreadable_config(archive, member):
        if getattr(member, "name", None) == config_path:
            return None
        return extractfile(archive, member)

    monkeypatch.setattr(tarfile.TarFile, "extractfile", unreadable_config)
    with pytest.raises(ContainerSbomError, match="config blob is unreadable"):
        _archive_identity(valid)


def test_archive_identity_wraps_non_tar_input(tmp_path):
    path = tmp_path / "not-a-tar.tar"
    path.write_bytes(b"not a tar archive")
    with pytest.raises(ContainerSbomError, match="cannot inspect Docker image archive"):
        _archive_identity(path)


def test_archive_identity_rejects_unreadable_manifest_stream(tmp_path, monkeypatch):
    path = tmp_path / "unreadable-manifest.tar"
    _write_tar(path, [("manifest.json", b"[]", False)])
    monkeypatch.setattr(tarfile.TarFile, "extractfile", lambda _archive, _member: None)

    with pytest.raises(ContainerSbomError, match="manifest.json is unreadable"):
        _archive_identity(path)
