from pathlib import Path

import pytest
from studio_data_engineering import SqliteRevisionStore


def test_sqlite_revision_store_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "ronin.db"
    store = SqliteRevisionStore(path)
    assert (
        store.save(
            project_id="p",
            pipeline_id="main",
            source_digest="digest-1",
            project_artifact_ref="artifact://p",
            pipeline_artifacts={"main.yaml": "artifact://main"},
            metadata_artifact_ref="artifact://metadata",
        )
        == 1
    )
    reopened = SqliteRevisionStore(path)
    latest = reopened.get_latest(project_id="p", pipeline_id="main")
    assert latest is not None
    assert latest["revision"] == 1
    assert latest["pipeline_artifacts"] == {"main.yaml": "artifact://main"}


def test_sqlite_revision_store_rejects_stale_write(tmp_path: Path) -> None:
    store = SqliteRevisionStore(tmp_path / "ronin.db")
    kwargs = {
        "project_id": "p",
        "pipeline_id": "main",
        "source_digest": "digest",
        "project_artifact_ref": "artifact://p",
        "pipeline_artifacts": {},
        "metadata_artifact_ref": "artifact://m",
    }
    store.save(**kwargs)
    with pytest.raises(ValueError, match="stale revision"):
        store.save(**kwargs, expected_revision=0)
