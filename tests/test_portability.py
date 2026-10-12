from __future__ import annotations

import pytest
from studio_core import portability
from studio_core.portability import (
    BindingRequest,
    BundleEntry,
    MigrationObjectReport,
    MigrationReport,
    RoninBundleManifest,
)


def test_bundle_manifest_round_trips_canonically() -> None:
    report = MigrationReport(
        source_platform="example",
        source_version="1",
        importer_version="1",
        objects=(
            MigrationObjectReport(
                source_type="dataset",
                source_id="source-1",
                status="translated",
                target_refs=("asset-1",),
            ),
        ),
    )
    manifest = RoninBundleManifest(
        entries=(
            BundleEntry(
                path="catalog/assets/asset-1.json",
                media_type="application/json",
                digest_algorithm="sha256",
                digest="00" * 32,
                size_bytes=123,
            ),
        ),
        migration_reports=(report,),
    )

    encoded = manifest.to_json()

    assert RoninBundleManifest.from_json(encoded) == manifest
    assert RoninBundleManifest.from_json(encoded).digest == manifest.digest


def test_migration_report_rejects_duplicate_source_objects() -> None:
    duplicate = MigrationObjectReport(
        source_type="dataset",
        source_id="same",
        status="exact",
    )

    with pytest.raises(ValueError, match="exactly once"):
        MigrationReport("example", "1", "1", (duplicate, duplicate))


def test_manual_decision_requires_explanation() -> None:
    with pytest.raises(ValueError, match="explanatory notes"):
        MigrationObjectReport(
            source_type="policy",
            source_id="policy-1",
            status="manual_decision",
        )


def test_bundle_paths_fail_closed() -> None:
    with pytest.raises(ValueError, match="^bundle path must be relative and use forward slashes$"):
        portability._require_safe_path("/absolute.json")
    with pytest.raises(ValueError, match="^bundle path must be relative and use forward slashes$"):
        portability._require_safe_path("a\\b.json")
    for path in ("../escape.json", "a/../escape.json", "a/./escape.json", "a//escape.json"):
        with pytest.raises(ValueError, match="^bundle path contains unsafe path components$"):
            portability._require_safe_path(path)
    assert portability._require_safe_path("a/b.json") == "a/b.json"


def test_binding_request_rejects_obvious_plaintext_credentials() -> None:
    with pytest.raises(ValueError, match="credential material"):
        BindingRequest("secret", "password=hunter2")


@pytest.mark.parametrize(
    "value",
    ["Bearer opaque-token", "-----BEGIN PRIVATE KEY-----", "PASSWORD=hunter2"],
)
def test_binding_request_rejects_each_credential_material_form(value: str) -> None:
    with pytest.raises(
        ValueError, match="^binding source_ref must not contain credential material$"
    ):
        portability._reject_credential_material(value, "binding source_ref")


def test_required_binding_keeps_report_unresolved() -> None:
    report = MigrationReport(
        source_platform="example",
        source_version="1",
        importer_version="1",
        objects=(
            MigrationObjectReport(
                source_type="connection",
                source_id="c1",
                status="translated",
                binding_requests=(BindingRequest("connection", "source-connection"),),
            ),
        ),
    )

    assert report.requires_manual_decision is True
    assert report.unresolved_bindings == (BindingRequest("connection", "source-connection"),)
