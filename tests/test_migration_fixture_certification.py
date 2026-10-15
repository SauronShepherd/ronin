from __future__ import annotations

from pathlib import Path

from tools.migration_fixture_certification import PROFILES, certify_fixture


def test_all_golden_profiles_execute_and_round_trip_through_native_bundle(tmp_path: Path) -> None:
    for profile, filename, discover, translate in PROFILES:
        evidence = certify_fixture(profile, filename, discover, translate, tmp_path)
        assert evidence["execution_status"] == "passed"
        assert evidence["workflow_imported"] is True
        assert evidence["bundle_roundtrip_digest"] == evidence["workflow_reexport_digest"]
