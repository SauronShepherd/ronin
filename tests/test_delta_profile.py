from __future__ import annotations

import pytest

from studio_lakehouse import DeltaCompatibilityProfile, DeltaTableStore, OpenTableIdentifier


def test_delta_profile_declares_supported_boundary() -> None:
    profile = DeltaCompatibilityProfile()
    assert profile.protocol_version == 1
    assert profile.supports_write("create")
    assert profile.supports_write("delete")
    assert "schema-evolution" in profile.unsupported_features


def test_delta_store_validates_mode_before_optional_dependency_loading(tmp_path) -> None:
    store = DeltaTableStore(tmp_path)
    assert store.compatibility.protocol_version == 1
    with pytest.raises(ValueError, match="unsupported Delta write mode"):
        store.write_rows(
            OpenTableIdentifier(("analytics",), "events"),
            ({"id": 1},),
            mode="invalid",  # type: ignore[arg-type]
        )


def test_delta_delete_removes_only_a_table_inside_the_warehouse(tmp_path) -> None:
    store = DeltaTableStore(tmp_path)
    identifier = OpenTableIdentifier(("analytics",), "events")
    table_path = tmp_path / "analytics" / "events"
    (table_path / "_delta_log").mkdir(parents=True)
    (table_path / "data.parquet").write_bytes(b"test")

    store.delete_table(identifier)

    assert not table_path.exists()
    with pytest.raises(FileNotFoundError, match="Delta table does not exist"):
        store.delete_table(identifier)


def test_delta_store_validates_projection_and_version_before_optional_dependency_loading(
    tmp_path,
) -> None:
    store = DeltaTableStore(tmp_path)
    identifier = OpenTableIdentifier(("analytics",), "events")
    with pytest.raises(ValueError, match="non-empty and trimmed"):
        store.read_rows(identifier, columns=(" id",))
    with pytest.raises(ValueError, match="non-negative"):
        store.read_rows(identifier, version="-1")
