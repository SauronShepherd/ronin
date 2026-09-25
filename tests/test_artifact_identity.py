from __future__ import annotations

from pathlib import Path

import pytest

from tools.artifact_identity import SCHEMA, build_manifest


def test_artifact_manifest_is_candidate_bound_and_hashed(tmp_path: Path) -> None:
    wheel = tmp_path / "ronin.whl"
    sdist = tmp_path / "ronin.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")

    manifest = build_manifest([sdist, wheel], commit="abc123")

    assert manifest["schema"] == SCHEMA
    assert manifest["commit"] == "abc123"
    assert [item["kind"] for item in manifest["artifacts"]] == ["sdist", "wheel"]
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])


def test_artifact_manifest_rejects_missing_or_empty_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_manifest([], commit="abc123")
    with pytest.raises(FileNotFoundError):
        build_manifest([tmp_path / "missing.whl"], commit="abc123")
