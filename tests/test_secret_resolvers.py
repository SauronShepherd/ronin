from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import SecretRef
from studio_storage import (
    CompositeSecretResolver,
    EnvironmentSecretResolver,
    MountedFileSecretResolver,
    SecretMaterial,
    SecretResolutionError,
)


def test_environment_secret_resolver_returns_redacted_material() -> None:
    resolver = EnvironmentSecretResolver({"RONIN_TEST_SECRET": "sensitive-value"})
    material = resolver.resolve(SecretRef("secret://env/RONIN_TEST_SECRET"))

    assert isinstance(material, SecretMaterial)
    assert material.reveal_text() == "sensitive-value"
    assert str(material) == "<redacted>"
    assert "sensitive-value" not in repr(material)


def test_environment_secret_resolver_fails_closed_for_missing_or_nested_names() -> None:
    resolver = EnvironmentSecretResolver({})
    with pytest.raises(SecretResolutionError, match="unavailable"):
        resolver.resolve(SecretRef("secret://env/MISSING"))
    with pytest.raises(SecretResolutionError, match="exactly one"):
        resolver.resolve(SecretRef("secret://env/group/name"))


def test_mounted_file_secret_resolver_reads_only_regular_files_under_root(tmp_path: Path) -> None:
    root = tmp_path / "secrets"
    root.mkdir()
    nested = root / "database"
    nested.mkdir()
    secret = nested / "password"
    secret.write_bytes(b"db-password")

    resolver = MountedFileSecretResolver(root)
    material = resolver.resolve(SecretRef("secret://file/database/password"))
    assert material.reveal_bytes() == b"db-password"


def test_mounted_file_secret_resolver_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "secrets"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside-secret")
    link = root / "link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    resolver = MountedFileSecretResolver(root)
    with pytest.raises(SecretResolutionError, match="symbolic links"):
        resolver.resolve(SecretRef("secret://file/link"))


def test_secret_reference_percent_decoded_traversal_is_rejected(tmp_path: Path) -> None:
    resolver = MountedFileSecretResolver(tmp_path)
    with pytest.raises(SecretResolutionError, match="unsafe path"):
        resolver.resolve(SecretRef("secret://file/%2E%2E/outside"))


def test_composite_resolver_dispatches_only_configured_backends(tmp_path: Path) -> None:
    environment = EnvironmentSecretResolver({"API_TOKEN": "token-value"})
    composite = CompositeSecretResolver(environment=environment)
    assert composite.resolve(SecretRef("secret://env/API_TOKEN")).reveal_text() == "token-value"

    with pytest.raises(SecretResolutionError, match="not configured"):
        composite.resolve(SecretRef("secret://file/unavailable"))


def test_secret_material_rejects_empty_values() -> None:
    with pytest.raises(SecretResolutionError, match="empty"):
        SecretMaterial(b"")
