"""Provider-neutral content-addressed artifact retention policy."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from studio_core import WorkspaceId
from studio_core.ml import MLRunRecord, RegisteredModelVersion

from .artifacts import ArtifactRef
from .ports import ArtifactStore, CatalogStore, PagedArtifactStore, WorkspaceStore

REQUIRED_ARTIFACT_REFERENCE_SOURCES = frozenset(
    {
        "catalog_revisions",
        "connector_sync_outputs",
        "data_engineering_revisions",
        "durable_execution_results",
        "durable_job_checkpoints",
        "local_files",
        "ml_runs",
        "registered_models",
        "synthetic_data_exports",
    }
)


@dataclass(frozen=True, slots=True)
class ArtifactRetentionPlan:
    """Non-destructive preview of unreferenced artifacts."""

    missing_sources: tuple[str, ...]
    candidate_digests: tuple[str, ...]
    inventory_truncated: bool = False

    @property
    def all_required_sources_supplied(self) -> bool:
        """Whether the caller supplied every known source family.

        This does not attest that a caller's data for those sources is exhaustive.
        """

        return not self.missing_sources and not self.inventory_truncated


class _MLArtifactReferenceStore(Protocol):
    def list_runs(self, workspace_id: WorkspaceId) -> tuple[MLRunRecord, ...]: ...

    def list_models(self, workspace_id: WorkspaceId) -> tuple[RegisteredModelVersion, ...]: ...


def plan_unreferenced(
    store: ArtifactStore,
    references_by_source: Mapping[str, Iterable[str]],
    *,
    page_size: int = 500,
    max_objects: int = 10_000,
    max_pages: int = 1_000,
) -> ArtifactRetentionPlan:
    """Preview stale digests only when every known reference source is present.

    This function never mutates the artifact store. Incomplete reference snapshots
    or artifact inventories over the configured bound produce no deletion candidates.
    """

    if page_size < 1 or page_size > 10_000:
        raise ValueError("retention page_size must be between 1 and 10000")
    if max_objects < 1:
        raise ValueError("retention max_objects must be positive")
    if max_pages < 1 or max_pages > 10_000:
        raise ValueError("retention max_pages must be between 1 and 10000")

    unknown_sources = set(references_by_source) - REQUIRED_ARTIFACT_REFERENCE_SOURCES
    if unknown_sources:
        source_names = ", ".join(sorted(unknown_sources))
        raise ValueError(f"unknown artifact reference sources: {source_names}")
    missing_sources = tuple(sorted(REQUIRED_ARTIFACT_REFERENCE_SOURCES - set(references_by_source)))
    if missing_sources:
        return ArtifactRetentionPlan(missing_sources, ())

    live_digests: set[str] = set()
    for source_digests in references_by_source.values():
        for digest in source_digests:
            _validate_digest(digest)
            live_digests.add(digest)

    stored_digests: set[str] = set()
    truncated = False
    if isinstance(store, PagedArtifactStore):
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages_seen = 0
        while True:
            page = store.list_digests_page(cursor=cursor, page_size=min(page_size, max_objects))
            pages_seen += 1
            for digest in page.digests:
                _validate_digest(digest)
            stored_digests.update(page.digests)
            if len(stored_digests) > max_objects or (
                page.truncated and len(stored_digests) >= max_objects
            ):
                truncated = True
                break
            if not page.truncated:
                break
            if pages_seen >= max_pages:
                truncated = True
                break
            if page.next_cursor is None:
                raise ValueError("truncated artifact inventory page is missing its cursor")
            if page.next_cursor in seen_cursors:
                raise ValueError("artifact inventory cursor repeated")
            seen_cursors.add(page.next_cursor)
            cursor = page.next_cursor
    else:
        return ArtifactRetentionPlan((), (), inventory_truncated=True)

    if truncated:
        return ArtifactRetentionPlan((), (), inventory_truncated=True)
    return ArtifactRetentionPlan((), tuple(sorted(stored_digests - live_digests)))


def _validate_digest(digest: object) -> None:
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise ValueError("artifact reference digests must be lowercase sha256 hex")


def discover_catalog_artifact_references(
    workspaces: WorkspaceStore, catalog: CatalogStore
) -> dict[str, tuple[str, ...]]:
    """Enumerate artifact references held by catalog revisions and local files."""

    catalog_digests: set[str] = set()
    file_digests: set[str] = set()
    for workspace in workspaces.list_workspaces():
        for asset in catalog.list_assets(workspace.id):
            for revision in catalog.list_revisions(workspace.id, asset.id):
                artifact_ref = dict(revision.metadata).get("artifact_ref")
                if artifact_ref is None:
                    continue
                digest = _digest_from_storage_ref(artifact_ref)
                catalog_digests.add(digest)
                if asset.kind == "file":
                    file_digests.add(digest)
    return {
        "catalog_revisions": tuple(sorted(catalog_digests)),
        "local_files": tuple(sorted(file_digests)),
    }


def discover_ml_artifact_references(
    workspaces: WorkspaceStore, registry: _MLArtifactReferenceStore
) -> dict[str, tuple[str, ...]]:
    """Enumerate artifacts held by ML runs and registered model versions."""

    run_digests: set[str] = set()
    model_digests: set[str] = set()
    for workspace in workspaces.list_workspaces():
        for run in registry.list_runs(workspace.id):
            run_digests.update(_digest_from_storage_ref(ref) for ref in run.artifact_refs)
            if run.runtime_snapshot_ref and run.runtime_snapshot_ref.startswith("artifact://"):
                run_digests.add(_digest_from_storage_ref(run.runtime_snapshot_ref))
        for model in registry.list_models(workspace.id):
            digest = model.artifact_digest.removeprefix("sha256:")
            _validate_digest(digest)
            ref_digest = _digest_from_storage_ref(model.artifact_ref)
            if ref_digest != digest:
                raise ValueError("registered model artifact reference and digest do not match")
            model_digests.add(digest)
    return {
        "ml_runs": tuple(sorted(run_digests)),
        "registered_models": tuple(sorted(model_digests)),
    }


def _digest_from_storage_ref(storage_ref: str) -> str:
    prefix = "artifact://sha256/"
    if not isinstance(storage_ref, str) or not storage_ref.startswith(prefix):
        raise ValueError("artifact storage reference must use artifact://sha256/<digest>")
    digest = storage_ref.removeprefix(prefix)
    _validate_digest(digest)
    return digest


def collect_unreferenced(store: ArtifactStore, live_digests: Iterable[str]) -> tuple[str, ...]:
    """Delete only stored digests absent from the caller-provided live set."""

    live = set(live_digests)
    if any(
        len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
        for digest in live
    ):
        raise ValueError("live artifact digests must be lowercase sha256 hex")
    deleted: list[str] = []
    for digest in store.list_digests():
        if digest in live:
            continue
        ref = ArtifactRef(
            role="retention",
            digest_algorithm="sha256",
            digest=digest,
            media_type=None,
            size_bytes=0,
            storage_ref=store.storage_ref_for_digest(digest),
        )
        if store.delete(ref):
            deleted.append(digest)
    return tuple(sorted(deleted))


__all__ = (
    "ArtifactRetentionPlan",
    "REQUIRED_ARTIFACT_REFERENCE_SOURCES",
    "collect_unreferenced",
    "discover_catalog_artifact_references",
    "discover_ml_artifact_references",
    "plan_unreferenced",
)
