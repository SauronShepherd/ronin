"""Content-addressed evidence persistence for pipeline worker results."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol

from studio_storage import ArtifactRef


class EvidenceStore(Protocol):
    def put_bytes(
        self, *, role: str, data: bytes, media_type: str | None = None
    ) -> ArtifactRef: ...


def persist_pipeline_evidence(
    store: EvidenceStore,
    *,
    project_id: str,
    run_id: str,
    output: Mapping[str, object],
    evidence: Mapping[str, object],
) -> ArtifactRef:
    if not project_id.strip() or not run_id.strip():
        raise ValueError("project_id and run_id must be non-empty")
    payload = {
        "version": "data-engineering.evidence.v1",
        "project_id": project_id,
        "run_id": run_id,
        "output": dict(output),
        "evidence": dict(evidence),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return store.put_bytes(
        role=f"data-engineering/{project_id}/{run_id}/preview-evidence.json",
        data=encoded,
        media_type="application/json",
    )


__all__ = ("EvidenceStore", "persist_pipeline_evidence")
