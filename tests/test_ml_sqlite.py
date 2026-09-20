"""SQLite persistence contract tests."""
# ruff: noqa: E501, E702

from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.services import LabService
from studio_ml.sqlite import SqliteMLLabStore


def test_sqlite_lab_and_pipeline_round_trip(tmp_path) -> None:
    store = SqliteMLLabStore(tmp_path / "ml.sqlite3", migration_now="2026-01-01T00:00:00.000000Z")
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "churn",
        "classification",
        (FeatureSpec("age"),),
    )
    service = LabService(store)
    service.create(WorkspaceId("ws"), lab)
    service.compile(WorkspaceId("ws"), lab.id)
    reopened = SqliteMLLabStore(
        tmp_path / "ml.sqlite3", migration_now="2026-01-01T00:00:00.000000Z"
    )
    assert reopened.get_lab(WorkspaceId("ws"), "churn") == lab
    assert reopened.get_pipeline(WorkspaceId("ws"), "churn") is not None
