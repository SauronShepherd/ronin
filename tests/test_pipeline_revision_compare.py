from __future__ import annotations

from studio_data_engineering import SqliteRevisionStore


def test_pipeline_revision_lookup_list_and_compare(tmp_path) -> None:
    store = SqliteRevisionStore(tmp_path / "revisions.db")
    store.save(
        project_id="p",
        pipeline_id="pipe",
        source_digest="sha256:a",
        project_artifact_ref="artifact:project-a",
        pipeline_artifacts={"node": "artifact:node-a"},
        metadata_artifact_ref="artifact:meta-a",
    )
    store.save(
        project_id="p",
        pipeline_id="pipe",
        source_digest="sha256:b",
        project_artifact_ref="artifact:project-b",
        pipeline_artifacts={"node": "artifact:node-b"},
        metadata_artifact_ref="artifact:meta-a",
        expected_revision=1,
    )
    first = store.get_revision(project_id="p", pipeline_id="pipe", revision=1)
    assert first["revision"] == 1
    assert len(first["revision_digest"]) == 64
    assert [
        item["revision"] for item in store.list_revisions(project_id="p", pipeline_id="pipe")
    ] == [2, 1]
    assert store.compare(project_id="p", pipeline_id="pipe", left_revision=1, right_revision=2) == {
        "left_revision": 1,
        "right_revision": 2,
        "source_changed": True,
        "project_artifact_changed": True,
        "pipeline_artifacts_changed": True,
        "metadata_changed": False,
    }
