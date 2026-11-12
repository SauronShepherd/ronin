from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.release_evidence import SCHEMA, EvidenceError
from tools.verify_release_artifacts import verify


def _bundle(path: str, digest: str) -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "schema": SCHEMA,
        "commit": "a" * 40,
        "records": [
            {
                "gate_id": "artifact",
                "status": "passed",
                "execution_scope": "complete",
                "commit": "a" * 40,
                "environment": {"fingerprint": "test"},
                "command": "test",
                "started_at": now,
                "ended_at": now,
                "artifacts": [path],
                "artifact_digests": {path: digest},
            }
        ],
    }


def test_verify_rehashes_relative_artifact_under_root(tmp_path: Path) -> None:
    artifact = tmp_path / "dist" / "app.whl"
    artifact.parent.mkdir()
    content = b"candidate"
    artifact.write_bytes(content)
    result = verify(_bundle("dist/app.whl", hashlib.sha256(content).hexdigest()), tmp_path)
    assert result["artifacts"][0]["path"] == "dist/app.whl"


@pytest.mark.parametrize("path", ["../outside", "/absolute/file", "dist/../file", "./file"])
def test_verify_rejects_paths_outside_relative_sandbox_contract(tmp_path: Path, path: str) -> None:
    with pytest.raises(EvidenceError, match="sandbox root"):
        verify(_bundle(path, "a" * 64), tmp_path)


def test_verify_rejects_symlink_components(tmp_path: Path) -> None:
    target = tmp_path / "outside"
    target.write_bytes(b"secret")
    link = tmp_path / "dist"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(EvidenceError, match="symlink"):
        verify(_bundle("dist/outside", hashlib.sha256(b"secret").hexdigest()), tmp_path)


def test_verify_rejects_mutated_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "app.whl"
    artifact.write_bytes(b"mutated")
    with pytest.raises(EvidenceError, match="digest mismatch"):
        verify(_bundle("app.whl", hashlib.sha256(b"original").hexdigest()), tmp_path)
