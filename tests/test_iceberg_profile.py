from studio_lakehouse import IcebergCompatibilityProfile


def test_iceberg_profile_declares_reference_boundary() -> None:
    profile = IcebergCompatibilityProfile()
    assert profile.spec_version == "1.4"
    assert {"create", "append", "snapshot-read"} <= set(profile.capabilities)
    assert "delete" in profile.capabilities
    assert "schema-evolution" in profile.unsupported_features
