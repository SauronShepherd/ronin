from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from tools import artifact_qualification as module


def _wheel(path: Path, *, record: bytes | None = None) -> None:
    record_name = "pyronin-0.1.0a2.dist-info/RECORD"
    payload = record or f"pyronin/__init__.py,,\n{record_name},,\n".encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("pyronin/__init__.py", "__version__='0.1.0a2'\n")
        archive.writestr(record_name, payload)


def test_artifact_record_binds_exact_bytes_and_record(tmp_path: Path) -> None:
    wheel = tmp_path / "pyronin-0.1.0a2-py3-none-any.whl"
    sdist = tmp_path / "pyronin-0.1.0a2.tar.gz"
    _wheel(wheel)
    sdist.write_bytes(b"sdist")
    result = module.artifact_record(wheel, sdist)
    assert result["package"] == "pyronin"
    assert result["version"] == "0.1.0a2"
    assert result["wheel"]["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert result["sdist"]["sha256"] == hashlib.sha256(b"sdist").hexdigest()
    assert len(result["wheel_record_sha256"]) == 64
    assert json.loads(module._canonical_json(result)) == result


def test_origin_must_be_site_packages_and_outside_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    site = tmp_path / "isolated" / "site-packages"
    checkout.mkdir()
    site.mkdir(parents=True)
    good = site / "pyronin.py"
    good.write_text("x=1")
    resolved = module.assert_installed_origin(good, checkout=checkout, site_packages=site)
    assert resolved == good.resolve()
    leaked = checkout / "pyronin.py"
    leaked.write_text("x=1")
    with pytest.raises(module.ArtifactQualificationError, match="leaked"):
        module.assert_installed_origin(leaked, checkout=checkout, site_packages=site)
    alien = tmp_path / "alien.py"
    alien.write_text("x=1")
    with pytest.raises(module.ArtifactQualificationError, match="outside isolated"):
        module.assert_installed_origin(alien, checkout=checkout, site_packages=site)


def test_license_binding_uses_artifact_digest_not_installed_metadata(tmp_path: Path) -> None:
    artifact = tmp_path / "dep.whl"
    artifact.write_bytes(b"candidate")
    digest = module.sha256_file(artifact)
    inventory = {
        "schema_version": 1,
        "packages": [
            {
                "package": "Demo_Pkg",
                "version": "2.0",
                "evidence_sha256": "a" * 64,
            }
        ],
    }
    result = module.bind_license_evidence(
        package="demo-pkg", version="2.0", artifact_sha256=digest, inventory=inventory
    )
    assert result == {
        "package": "demo-pkg",
        "version": "2.0",
        "artifact_sha256": digest,
        "license_evidence_sha256": "a" * 64,
    }


def test_license_binding_fails_closed_on_missing_or_bad_evidence() -> None:
    with pytest.raises(module.ArtifactQualificationError, match="found 0"):
        module.bind_license_evidence(
            package="x", version="1", artifact_sha256="b" * 64,
            inventory={"schema_version": 1, "packages": []},
        )
    with pytest.raises(module.ArtifactQualificationError, match="invalid evidence"):
        module.bind_license_evidence(
            package="x", version="1", artifact_sha256="b" * 64,
            inventory={
                "schema_version": 1,
                "packages": [
                    {"package": "x", "version": "1", "evidence_sha256": "bad"}
                ],
            },
        )


def test_work_root_inside_checkout_is_rejected(tmp_path: Path) -> None:
    checkout = tmp_path / "repo"
    checkout.mkdir()
    inside = checkout / "work"
    inside.mkdir()
    with pytest.raises(module.ArtifactQualificationError, match="outside checkout"):
        module.qualify_pyronin(checkout, inside)
