import os

import pytest
from studio_core import SecretRef
from studio_storage import MountedFileSecretResolver, SecretResolutionError


def test_mounted_file_secret_resolves_without_exposing_material(tmp_path):
    path = tmp_path / "token"
    path.write_bytes(b"private-token")
    if os.name != "nt":
        path.chmod(0o600)
    material = MountedFileSecretResolver(tmp_path).resolve(SecretRef("secret://file/token"))
    assert material.reveal_bytes() == b"private-token"
    assert "private-token" not in repr(material)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not authoritative on Windows")
def test_mounted_file_secret_rejects_broad_permissions(tmp_path):
    path = tmp_path / "token"
    path.write_bytes(b"private-token")
    path.chmod(0o644)
    with pytest.raises(SecretResolutionError, match="permissions"):
        MountedFileSecretResolver(tmp_path).resolve(SecretRef("secret://file/token"))
