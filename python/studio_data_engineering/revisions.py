"""Revision application service for SDP-backed Data Enginerring projects."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from studio_storage import ArtifactRef

from .sdp_adapter import SdpProjectSource


class RevisionConflict(ValueError):
    """An optimistic revision write would overwrite newer state."""


class RevisionArtifactStore(Protocol):
    def put_bytes(
        self, *, role: str, data: bytes, media_type: str | None = None
    ) -> ArtifactRef: ...


class RevisionRecordStore(Protocol):
    def get_latest(self, *, project_id: str, pipeline_id: str) -> Mapping[str, object] | None: ...

    def save(
        self,
        *,
        project_id: str,
        pipeline_id: str,
        source_digest: str,
        project_artifact_ref: str,
        pipeline_artifacts: Mapping[str, str],
        metadata_artifact_ref: str,
        expected_revision: int | None = None,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class PipelineRevisionRecord:
    project_id: str
    pipeline_id: str
    revision: int
    source_digest: str
    project_artifact: ArtifactRef
    pipeline_artifacts: tuple[tuple[str, ArtifactRef], ...]
    metadata_artifact: ArtifactRef


class RevisionApplication:
    """Persist immutable SDP source documents through Ronin's artifact port."""

    def __init__(
        self,
        artifacts: RevisionArtifactStore,
        records: RevisionRecordStore | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._records = records
        self._latest: dict[tuple[str, str], int] = {}

    def import_sdp(
        self,
        *,
        project_id: str,
        pipeline_id: str,
        source: SdpProjectSource,
        expected_revision: int | None = None,
    ) -> PipelineRevisionRecord:
        key = (project_id, pipeline_id)
        latest = self._latest.get(key, 0)
        if self._records is not None and key not in self._latest:
            existing = self._records.get_latest(
                project_id=project_id, pipeline_id=pipeline_id
            )
            if existing is not None:
                latest = int(existing["revision"])
        if expected_revision is not None and expected_revision != latest:
            raise RevisionConflict(
                f"stale revision: expected {expected_revision}, current {latest}"
            )
        revision = latest + 1
        project_artifact = self._artifacts.put_bytes(
            role=f"data-engineering/{project_id}/{pipeline_id}/project.yaml",
            data=source.project_yaml,
            media_type="application/yaml",
        )
        pipeline_artifacts = tuple(
            (
                name,
                self._artifacts.put_bytes(
                    role=f"data-engineering/{project_id}/{pipeline_id}/{name}",
                    data=payload,
                    media_type="application/yaml",
                ),
            )
            for name, payload in source.pipeline_documents
        )
        metadata = {
            "project_id": project_id,
            "pipeline_id": pipeline_id,
            "revision": revision,
            "source_digest": source.source_digest,
            "artifacts": [
                {"name": name, "digest": ref.digest} for name, ref in pipeline_artifacts
            ],
        }
        metadata_artifact = self._artifacts.put_bytes(
            role=f"data-engineering/{project_id}/{pipeline_id}/revision-{revision}.json",
            data=json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode(),
            media_type="application/json",
        )
        if self._records is not None:
            revision = self._records.save(
                project_id=project_id,
                pipeline_id=pipeline_id,
                source_digest=source.source_digest,
                project_artifact_ref=project_artifact.storage_ref,
                pipeline_artifacts={name: ref.storage_ref for name, ref in pipeline_artifacts},
                metadata_artifact_ref=metadata_artifact.storage_ref,
                expected_revision=latest,
            )
        self._latest[key] = revision
        return PipelineRevisionRecord(
            project_id,
            pipeline_id,
            revision,
            source.source_digest,
            project_artifact,
            pipeline_artifacts,
            metadata_artifact,
        )


__all__ = ("PipelineRevisionRecord", "RevisionApplication", "RevisionConflict")
