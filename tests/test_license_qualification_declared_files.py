from __future__ import annotations

import pytest
from tools.license_qualification import (
    LicenseQualificationError,
    package_evidence_sha256,
    qualify,
)

_LOCK_SHA = "0" * 64
_HASH = "a" * 64


def test_qualify_rejects_declared_license_file_without_installed_evidence() -> None:
    entry: dict[str, object] = {
        "package": "alpha",
        "version": "1.0",
        "direct": True,
        "source": "https://example.invalid/alpha",
        "declared_license": "MIT",
        "declared_license_files": ["THIRD_PARTY_TERMS.txt"],
        "license_files": [
            {
                "path": "alpha-1.0.dist-info/licenses/LICENSE.custom",
                "sha256": _HASH,
            }
        ],
    }
    entry["evidence_sha256"] = package_evidence_sha256(entry)
    inventory: dict[str, object] = {
        "schema_version": 1,
        "lock_file": "requirements-dev.lock",
        "lock_sha256": _LOCK_SHA,
        "packages": [entry],
    }
    policy: dict[str, object] = {
        "schema_version": 1,
        "project_notice": "not_required",
        "project_notice_rationale": "reviewed fixture obligations",
        "reviews": {
            "alpha==1.0": {
                "decision": "allow",
                "evidence_sha256": entry["evidence_sha256"],
                "notice_required": False,
                "attribution_required": False,
                "rationale": "reviewed fixture",
            }
        },
    }

    with pytest.raises(
        LicenseQualificationError,
        match="declared License-File evidence missing from inventory",
    ):
        qualify(
            inventory,
            policy,
            {"alpha": "1.0"},
            expected_lock_sha256=_LOCK_SHA,
            expected_direct={"alpha"},
        )


def test_qualify_rejects_noncanonical_installed_legal_file_path() -> None:
    entry: dict[str, object] = {
        "package": "alpha",
        "version": "1.0",
        "direct": True,
        "source": "https://example.invalid/alpha",
        "declared_license": "MIT",
        "declared_license_files": [],
        "license_files": [{"path": "../LICENSE", "sha256": _HASH}],
    }
    entry["evidence_sha256"] = package_evidence_sha256(entry)
    inventory: dict[str, object] = {
        "schema_version": 1,
        "lock_file": "requirements-dev.lock",
        "lock_sha256": _LOCK_SHA,
        "packages": [entry],
    }
    policy: dict[str, object] = {
        "schema_version": 1,
        "project_notice": "not_required",
        "project_notice_rationale": "reviewed fixture obligations",
        "reviews": {
            "alpha==1.0": {
                "decision": "allow",
                "evidence_sha256": entry["evidence_sha256"],
                "notice_required": False,
                "attribution_required": False,
                "rationale": "reviewed fixture",
            }
        },
    }

    with pytest.raises(LicenseQualificationError, match="invalid license_files"):
        qualify(
            inventory,
            policy,
            {"alpha": "1.0"},
            expected_lock_sha256=_LOCK_SHA,
            expected_direct={"alpha"},
        )
