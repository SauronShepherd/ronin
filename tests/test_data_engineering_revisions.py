from pathlib import Path

import pytest
from studio_data_engineering import (
    RevisionApplication,
    RevisionConflict,
    SdpProjectSource,
    SqliteRevisionStore,
)
from studio_storage import LocalArtifactStore


def test_sdp_import_persists_content_addressed_revision(tmp_path: Path) -> None:
    service = RevisionApplication(LocalArtifactStore(tmp_path / "artifacts"))
    source = SdpProjectSource(
        "retail", b"name: retail\n", (("pipelines/main.yaml", b"nodes: []\n"),)
    )
    record = service.import_sdp(
        project_id="project-1", pipeline_id="main", source=source
    )
    assert record.revision == 1
    assert record.source_digest == source.source_digest
    assert record.project_artifact.digest
    assert record.pipeline_artifacts[0][1].digest
    assert record.metadata_artifact.media_type == "application/json"


def test_sdp_import_uses_optimistic_revision_lock(tmp_path: Path) -> None:
    service = RevisionApplication(LocalArtifactStore(tmp_path / "artifacts"))
    source = SdpProjectSource("retail", b"name: retail\n", ())
    service.import_sdp(project_id="p", pipeline_id="main", source=source)
    with pytest.raises(RevisionConflict):
        service.import_sdp(
            project_id="p",
            pipeline_id="main",
            source=source,
            expected_revision=0,
        )


def test_revision_application_uses_durable_revision_store(tmp_path: Path) -> None:
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    records = SqliteRevisionStore(tmp_path / "ronin.db")
    service = RevisionApplication(artifacts, records)
    source = SdpProjectSource("retail", b"name: retail\n", ())
    first = service.import_sdp(project_id="p", pipeline_id="main", source=source)
    assert first.revision == 1

    reopened = RevisionApplication(artifacts, SqliteRevisionStore(tmp_path / "ronin.db"))
    second = reopened.import_sdp(
        project_id="p", pipeline_id="main", source=source, expected_revision=1
    )
    assert second.revision == 2
