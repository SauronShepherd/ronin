"""SQLite persistence contract tests."""
# ruff: noqa: E501, E702

import json
from pathlib import Path

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


def test_sqlite_preserves_lab_v1_unknown_metadata_after_reopen(tmp_path) -> None:
    fixture = Path(__file__).parent / "fixtures/contracts/ml-lab-v1-clustering.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    lab = Lab.from_payload(payload)
    store = SqliteMLLabStore(
        tmp_path / "metadata.sqlite3", migration_now="2026-01-01T00:00:00.000000Z"
    )

    store.put_lab(WorkspaceId("ws"), lab)
    reopened = SqliteMLLabStore(
        tmp_path / "metadata.sqlite3", migration_now="2026-01-01T00:00:00.000000Z"
    )

    persisted = reopened.get_lab(WorkspaceId("ws"), lab.id)
    assert persisted is not None
    assert persisted.to_payload() == payload
    assert persisted.digest == lab.digest
