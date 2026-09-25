from __future__ import annotations

import pytest

from studio_data_engineering import SqliteRevisionStore


def test_pipeline_archive_preserves_history_and_blocks_new_revisions(tmp_path) -> None:
    store = SqliteRevisionStore(tmp_path / "revisions.db")
    kwargs = {
        "project_id": "p",
        "pipeline_id": "pipe",
        "source_digest": "sha256:a",
        "project_artifact_ref": "artifact:p",
        "pipeline_artifacts": {"node": "artifact:n"},
        "metadata_artifact_ref": "artifact:m",
    }
    store.save(**kwargs)
    assert store.archive(project_id="p", pipeline_id="pipe") is True
    assert store.is_archived(project_id="p", pipeline_id="pipe")
    assert store.get_latest(project_id="p", pipeline_id="pipe")["revision"] == 1
    with pytest.raises(ValueError, match="archived"):
        store.save(**kwargs, expected_revision=1)
    assert store.archive(project_id="p", pipeline_id="pipe") is False


def test_pipeline_revision_rejects_empty_artifact_identity(tmp_path) -> None:
    store = SqliteRevisionStore(tmp_path / "revisions.db")
    with pytest.raises(ValueError, match="non-empty"):
        store.save(
            project_id="p",
            pipeline_id="pipe",
            source_digest="",
            project_artifact_ref="artifact:p",
            pipeline_artifacts={"node": "artifact:n"},
            metadata_artifact_ref="artifact:m",
        )
