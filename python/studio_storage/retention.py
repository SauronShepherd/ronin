"""Provider-neutral content-addressed artifact retention policy."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from studio_core import AssetId, AssetRevision, CatalogAsset, Workspace, WorkspaceId
from studio_core.ml import MLRunRecord, RegisteredModelVersion
from studio_orchestrator import EvidenceAvailability, JobStore

from .artifacts import ArtifactRef
from .ports import ArtifactStore, PagedArtifactStore


class _BoundedWorkspaceInventory(Protocol):
    def list_workspaces(self, *, limit: int | None = None) -> tuple[Workspace, ...]: ...


class _BoundedCatalogInventory(Protocol):
    def list_assets(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[CatalogAsset, ...]: ...

    def list_revisions(
        self, workspace_id: WorkspaceId, asset_id: AssetId, *, limit: int | None = None
    ) -> tuple[AssetRevision, ...]: ...


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
    def list_runs(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[MLRunRecord, ...]: ...

    def list_models(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[RegisteredModelVersion, ...]: ...


class _ConnectorOutputReferenceStore(Protocol):
    def list_committed_outputs(
        self, *, max_outputs: int = 10_000
    ) -> tuple[tuple[str, str], ...]: ...


class _DataEngineeringRevisionStore(Protocol):
    def list_all_revisions(
        self, *, max_revisions: int = 10_000
    ) -> tuple[dict[str, object], ...]: ...


class _SyntheticExportRun(Protocol):
    run_id: str


class _SyntheticExportStore(Protocol):
    def snapshot(self) -> tuple[_SyntheticExportRun, ...]: ...

    def artifacts(self, run_id: str) -> tuple[dict[str, object], ...]: ...


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


def _validate_retention_bound(limit: int, name: str) -> None:
    if limit < 1:
        raise ValueError(f"retention {name} bound must be positive")


def discover_catalog_artifact_references(
    workspaces: _BoundedWorkspaceInventory,
    catalog: _BoundedCatalogInventory,
    *,
    max_workspaces: int = 10_000,
    max_assets: int = 100_000,
    max_revisions: int = 1_000_000,
) -> dict[str, tuple[str, ...]]:
    """Enumerate artifact references held by catalog revisions and local files."""

    _validate_retention_bound(max_workspaces, "workspace")
    _validate_retention_bound(max_assets, "catalog asset")
    _validate_retention_bound(max_revisions, "catalog revision")

    catalog_digests: set[str] = set()
    file_digests: set[str] = set()
    assets_seen = 0
    revisions_seen = 0
    for workspace in workspaces.list_workspaces(limit=max_workspaces):
        assets = catalog.list_assets(workspace.id, limit=max(1, max_assets - assets_seen))
        assets_seen += len(assets)
        if assets_seen > max_assets:
            raise ValueError("catalog asset inventory exceeded its global bound")
        for asset in assets:
            revisions = catalog.list_revisions(
                workspace.id, asset.id, limit=max(1, max_revisions - revisions_seen)
            )
            revisions_seen += len(revisions)
            if revisions_seen > max_revisions:
                raise ValueError("catalog revision inventory exceeded its global bound")
            for revision in revisions:
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
    workspaces: _BoundedWorkspaceInventory,
    registry: _MLArtifactReferenceStore,
    *,
    max_workspaces: int = 10_000,
    max_runs: int = 100_000,
    max_models: int = 100_000,
) -> dict[str, tuple[str, ...]]:
    """Enumerate artifacts held by ML runs and registered model versions."""

    _validate_retention_bound(max_workspaces, "workspace")
    _validate_retention_bound(max_runs, "ML run")
    _validate_retention_bound(max_models, "registered model")

    run_digests: set[str] = set()
    model_digests: set[str] = set()
    runs_seen = 0
    models_seen = 0
    for workspace in workspaces.list_workspaces(limit=max_workspaces):
        runs = registry.list_runs(workspace.id, limit=max(1, max_runs - runs_seen))
        runs_seen += len(runs)
        if runs_seen > max_runs:
            raise ValueError("ML run inventory exceeded its global bound")
        for run in runs:
            run_digests.update(_digest_from_storage_ref(ref) for ref in run.artifact_refs)
            if run.runtime_snapshot_ref and run.runtime_snapshot_ref.startswith("artifact://"):
                run_digests.add(_digest_from_storage_ref(run.runtime_snapshot_ref))
        models = registry.list_models(workspace.id, limit=max(1, max_models - models_seen))
        models_seen += len(models)
        if models_seen > max_models:
            raise ValueError("registered model inventory exceeded its global bound")
        for model in models:
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


def discover_durable_job_artifact_references(
    jobs: JobStore,
    *,
    page_size: int = 100,
    max_pages: int = 1_000,
    max_runs: int = 100_000,
) -> dict[str, tuple[str, ...]]:
    """Enumerate artifact references persisted by durable job execution.

    Job listing is globally paged and bounded. Any incomplete page walk or
    malformed persisted cell payload raises, so callers cannot mistake a partial
    snapshot for a complete reference source.
    """

    if page_size < 1 or page_size > 100:
        raise ValueError("job page_size must be between 1 and 100")
    if max_pages < 1 or max_pages > 10_000:
        raise ValueError("job max_pages must be between 1 and 10000")
    if max_runs < 1:
        raise ValueError("job max_runs must be positive")

    execution_digests: set[str] = set()
    checkpoint_digests: set[str] = set()
    cursor: str | None = None
    seen_cursors: set[str] = set()
    runs_seen = 0
    for _ in range(max_pages):
        page = jobs.list_jobs(
            project_id=None,
            project_ids=None,
            state=None,
            limit=page_size,
            cursor=cursor,
        )
        for job in page.items:
            run_ids = jobs.list_run_ids_for_job(job.id)
            if not run_ids:
                raise ValueError("durable job is missing its run identity")
            runs_seen += len(run_ids)
            if runs_seen > max_runs:
                raise ValueError("durable job inventory exceeded its run bound")
            for run_id in run_ids:
                for evidence in jobs.read_evidence(run_id):
                    if evidence.availability is not EvidenceAvailability.AVAILABLE:
                        continue
                    if evidence.storage_ref and evidence.storage_ref.startswith("artifact://"):
                        digest = _digest_from_storage_ref(evidence.storage_ref)
                        if evidence.digest != digest:
                            raise ValueError(
                                "durable execution evidence reference and digest do not match"
                            )
                        execution_digests.add(digest)
                for result in jobs.read_cell_results(run_id):
                    try:
                        payload = json.loads(result.result_json)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise ValueError("durable cell result contains invalid JSON") from exc
                    for reference in _artifact_references_in(payload):
                        digest = _digest_from_storage_ref(reference["storage_ref"])
                        if reference["digest"] != digest:
                            raise ValueError(
                                "durable cell artifact reference and digest do not match"
                            )
                        role = reference.get("role")
                        if role == "ml-node-checkpoint":
                            checkpoint_digests.add(digest)
                        else:
                            execution_digests.add(digest)
        next_cursor = page.next_cursor
        if next_cursor is None:
            return {
                "durable_execution_results": tuple(sorted(execution_digests)),
                "durable_job_checkpoints": tuple(sorted(checkpoint_digests)),
            }
        if next_cursor in seen_cursors or next_cursor == cursor:
            raise ValueError("durable job inventory cursor repeated")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise ValueError("durable job inventory exceeded its page bound")


def discover_connector_artifact_references(
    checkpoints: _ConnectorOutputReferenceStore, *, max_outputs: int = 10_000
) -> dict[str, tuple[str, ...]]:
    """Discover ArtifactStore outputs committed through connector checkpoints."""

    digests: set[str] = set()
    for storage_ref, declared_digest in checkpoints.list_committed_outputs(max_outputs=max_outputs):
        if not storage_ref.startswith("artifact://"):
            continue
        digest = _digest_from_storage_ref(storage_ref)
        _validate_digest(declared_digest)
        if digest != declared_digest:
            raise ValueError("connector output reference and digest do not match")
        digests.add(digest)
    return {"connector_sync_outputs": tuple(sorted(digests))}


def discover_data_engineering_artifact_references(
    revisions: _DataEngineeringRevisionStore, *, max_revisions: int = 10_000
) -> dict[str, tuple[str, ...]]:
    """Discover project, pipeline, and metadata artifacts for every stored revision."""

    digests: set[str] = set()
    records = revisions.list_all_revisions(max_revisions=max_revisions)
    for record in records:
        refs: list[object] = [
            record.get("project_artifact_ref"),
            record.get("metadata_artifact_ref"),
        ]
        pipeline_artifacts = record.get("pipeline_artifacts")
        if not isinstance(pipeline_artifacts, Mapping):
            raise ValueError("Data Engineering revision has invalid pipeline artifacts")
        refs.extend(pipeline_artifacts.values())
        for storage_ref in refs:
            digests.add(_digest_from_storage_ref(storage_ref))
    return {"data_engineering_revisions": tuple(sorted(digests))}


def discover_synthetic_data_artifact_references(
    exports: _SyntheticExportStore,
    *,
    max_runs: int = 100_000,
    max_exports: int = 100_000,
) -> dict[str, tuple[str, ...]]:
    """Discover persisted synthetic-data exports within explicit run/export bounds."""

    if max_runs < 1:
        raise ValueError("synthetic export max_runs must be positive")
    if max_exports < 1:
        raise ValueError("synthetic export max_exports must be positive")
    runs = exports.snapshot()
    if len(runs) > max_runs:
        raise ValueError("synthetic export inventory exceeded its run bound")
    digests: set[str] = set()
    exports_seen = 0
    for run in runs:
        if not isinstance(run.run_id, str) or not run.run_id:
            raise ValueError("synthetic run has an invalid identity")
        records = exports.artifacts(run.run_id)
        exports_seen += len(records)
        if exports_seen > max_exports:
            raise ValueError("synthetic export inventory exceeded its export bound")
        for record in records:
            storage_ref = record.get("storage_ref")
            digest = record.get("digest")
            if not isinstance(digest, str):
                raise ValueError("synthetic export has an invalid digest")
            _validate_digest(digest)
            if _digest_from_storage_ref(storage_ref) != digest:
                raise ValueError("synthetic export reference and digest do not match")
            digests.add(digest)
    return {"synthetic_data_exports": tuple(sorted(digests))}


def discover_artifact_references(
    workspaces: _BoundedWorkspaceInventory,
    catalog: _BoundedCatalogInventory,
    ml_registry: _MLArtifactReferenceStore,
    jobs: JobStore,
    connector_checkpoints: _ConnectorOutputReferenceStore,
    data_engineering_revisions: _DataEngineeringRevisionStore,
    synthetic_exports: _SyntheticExportStore,
    *,
    job_page_size: int = 100,
    max_job_pages: int = 1_000,
    max_job_runs: int = 100_000,
    max_workspaces: int = 10_000,
    max_catalog_assets: int = 100_000,
    max_catalog_revisions: int = 1_000_000,
    max_ml_runs: int = 100_000,
    max_registered_models: int = 100_000,
    max_connector_outputs: int = 10_000,
    max_data_engineering_revisions: int = 10_000,
    max_synthetic_runs: int = 100_000,
    max_synthetic_exports: int = 100_000,
) -> dict[str, tuple[str, ...]]:
    """Build the complete known reference snapshot from every producer store.

    Any source read or bound failure raises before a caller can pass a partial map
    to the retention planner.
    """

    sources = (
        discover_catalog_artifact_references(
            workspaces,
            catalog,
            max_workspaces=max_workspaces,
            max_assets=max_catalog_assets,
            max_revisions=max_catalog_revisions,
        ),
        discover_ml_artifact_references(
            workspaces,
            ml_registry,
            max_workspaces=max_workspaces,
            max_runs=max_ml_runs,
            max_models=max_registered_models,
        ),
        discover_durable_job_artifact_references(
            jobs,
            page_size=job_page_size,
            max_pages=max_job_pages,
            max_runs=max_job_runs,
        ),
        discover_connector_artifact_references(
            connector_checkpoints, max_outputs=max_connector_outputs
        ),
        discover_data_engineering_artifact_references(
            data_engineering_revisions, max_revisions=max_data_engineering_revisions
        ),
        discover_synthetic_data_artifact_references(
            synthetic_exports,
            max_runs=max_synthetic_runs,
            max_exports=max_synthetic_exports,
        ),
    )
    references: dict[str, tuple[str, ...]] = {}
    for source in sources:
        duplicates = set(references) & set(source)
        if duplicates:
            raise RuntimeError(
                f"duplicate artifact reference sources: {', '.join(sorted(duplicates))}"
            )
        references.update(source)
    missing = REQUIRED_ARTIFACT_REFERENCE_SOURCES - set(references)
    if missing:
        raise RuntimeError(
            f"artifact reference snapshot is missing sources: {', '.join(sorted(missing))}"
        )
    return references


def _artifact_references_in(value: object) -> Iterable[dict[str, str]]:
    """Yield validated reference-shaped objects nested in persisted JSON."""

    if isinstance(value, dict):
        storage_ref = value.get("storage_ref")
        digest = value.get("digest")
        if storage_ref is not None:
            if not isinstance(storage_ref, str) or not isinstance(digest, str):
                raise ValueError("durable cell artifact reference is incomplete")
            ref: dict[str, str] = {"storage_ref": storage_ref, "digest": digest}
            role = value.get("role")
            if role is not None:
                if not isinstance(role, str):
                    raise ValueError("durable cell artifact role is invalid")
                ref["role"] = role
            yield ref
        for nested in value.values():
            yield from _artifact_references_in(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _artifact_references_in(nested)


def _digest_from_storage_ref(storage_ref: object) -> str:
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
    "discover_connector_artifact_references",
    "discover_data_engineering_artifact_references",
    "discover_durable_job_artifact_references",
    "discover_artifact_references",
    "discover_ml_artifact_references",
    "discover_synthetic_data_artifact_references",
    "plan_unreferenced",
)
