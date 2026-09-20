"""Publish generated tables as governed catalog assets with lineage."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore

from .engine import GenerationResult


@dataclass(frozen=True, slots=True)
class PublishedSyntheticOutput:
    asset: CatalogAsset
    revision: AssetRevision
    lineage: LineageEdge


class SyntheticOutputPublisher:
    """Adapter joining the synthetic result to Ronin's catalog/lineage stores."""

    def __init__(self, catalog: SqliteCatalogStore) -> None:
        self._catalog = catalog

    def publish(
        self,
        *,
        workspace_id: WorkspaceId,
        source: AssetRef,
        output_asset_id: str,
        output_version: str,
        result: GenerationResult,
        run_id: str,
        now: Instant | str,
    ) -> PublishedSyntheticOutput:
        if not run_id.strip():
            raise ValueError("run_id is required for synthetic output lineage")
        asset = CatalogAsset(
            id=AssetId(output_asset_id),
            kind="dataset",
            name=output_asset_id.rsplit(".", 1)[-1],
            tags=("synthetic", "synthetic-data-studio"),
            classifications=("synthetic",),
            properties=(("generation_run_id", run_id),),
        )
        revision_ref = AssetRef(asset.id, AssetVersion(output_version))
        payload = {
            "tables": [{"name": table.name, "rows": list(table.rows)} for table in result.tables],
            "plan_fingerprint": result.plan_fingerprint,
        }
        content_digest = "sha256:" + hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        schema_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                {table.name: sorted(table.rows[0]) if table.rows else [] for table in result.tables},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        revision = AssetRevision(
            revision_ref,
            schema_digest=schema_digest,
            content_digest=content_digest,
            metadata=(
                ("synthetic", "true"),
                ("plan_fingerprint", result.plan_fingerprint),
                ("run_id", run_id),
            ),
        )
        lineage = LineageEdge(
            source=source,
            target=revision_ref,
            operation="transform",
            mode="observed",
            execution_ref=run_id,
        )
        self._catalog.create_asset(workspace_id, asset, now=now)
        self._catalog.put_revision(workspace_id, revision, now=now)
        self._catalog.put_lineage(workspace_id, lineage, now=now)
        return PublishedSyntheticOutput(asset, revision, lineage)


def make_publication_hook(
    publisher: SyntheticOutputPublisher,
    *,
    workspace_id: WorkspaceId,
    source: AssetRef,
    output_asset_id: str,
    now: Instant | str,
) -> Callable[[str, GenerationResult], None]:
    """Build the application hook that publishes each completed generation."""

    def publish(run_id: str, result: GenerationResult) -> None:
        publisher.publish(
            workspace_id=workspace_id,
            source=source,
            output_asset_id=output_asset_id,
            output_version=run_id,
            result=result,
            run_id=run_id,
            now=now,
        )

    return publish


__all__ = ["PublishedSyntheticOutput", "SyntheticOutputPublisher", "make_publication_hook"]
