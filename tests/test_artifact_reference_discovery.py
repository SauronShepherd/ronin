from __future__ import annotations

import json
from contextlib import contextmanager
from hashlib import sha256
from types import SimpleNamespace

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    Workspace,
    WorkspaceId,
)
from studio_core.ml import (
    ExperimentId,
    MLRunId,
    MLRunRecord,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import EvidenceAvailability
from studio_storage import (
    REQUIRED_ARTIFACT_REFERENCE_SOURCES,
    LocalArtifactStore,
    collect_referenced_artifacts,
    discover_artifact_references,
    discover_catalog_artifact_references,
    discover_data_engineering_query_evidence_references,
    discover_durable_job_artifact_references,
    discover_ml_artifact_references,
    discover_synthetic_data_artifact_references,
    plan_unreferenced,
)

WORKSPACE = Workspace(WorkspaceId("ws-retention"), "Retention test")


class _WorkspaceStore:
    def list_workspaces(self, *, limit: int | None = None) -> tuple[Workspace, ...]:
        del limit
        return (WORKSPACE,)


class _CatalogStore:
    def __init__(self, entries: tuple[tuple[CatalogAsset, AssetRevision], ...]) -> None:
        self._entries = entries

    def list_assets(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[CatalogAsset, ...]:
        assert workspace_id == WORKSPACE.id
        values = tuple(asset for asset, _revision in self._entries)
        if limit is not None and len(values) > limit:
            raise ValueError("catalog asset inventory exceeded its bound")
        return values

    def list_revisions(
        self, workspace_id: WorkspaceId, asset_id: AssetId, *, limit: int | None = None
    ) -> tuple[AssetRevision, ...]:
        assert workspace_id == WORKSPACE.id
        values = tuple(revision for asset, revision in self._entries if asset.id == asset_id)
        if limit is not None and len(values) > limit:
            raise ValueError("catalog revision inventory exceeded its bound")
        return values


class _MLRegistry:
    def __init__(
        self,
        runs: tuple[MLRunRecord, ...],
        models: tuple[RegisteredModelVersion, ...],
    ) -> None:
        self._runs = runs
        self._models = models

    def list_runs(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[MLRunRecord, ...]:
        assert workspace_id == WORKSPACE.id
        if limit is not None and len(self._runs) > limit:
            raise ValueError("ML run inventory exceeded its bound")
        return self._runs

    def list_models(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[RegisteredModelVersion, ...]:
        assert workspace_id == WORKSPACE.id
        if limit is not None and len(self._models) > limit:
            raise ValueError("registered model inventory exceeded its bound")
        return self._models


class _ConnectorOutputStore:
    def list_committed_outputs(self, *, max_outputs: int = 10_000):
        del max_outputs
        return ()


class _DataEngineeringRevisionStore:
    def list_all_revisions(self, *, max_revisions: int = 10_000):
        del max_revisions
        return ()


class _DataEngineeringQueryEvidenceStore:
    def __init__(self, records=()):
        self.records = tuple(records)

    def list_evidence_references(self, *, max_references: int = 10_000):
        if len(self.records) > max_references:
            raise ValueError("QueryFlux evidence reference inventory exceeded its bound")
        return self.records


class _SyntheticExportStore:
    def __init__(self, runs=(), records=None):
        self.runs = tuple(runs)
        self.records = records or {}
        self.snapshot_limit = None
        self.artifact_limits = []

    def snapshot(self, *, limit=None):
        self.snapshot_limit = limit
        return self.runs if limit is None else self.runs[:limit]

    def artifacts(self, run_id: str, *, limit=None):
        self.artifact_limits.append(limit)
        records = self.records.get(run_id, ())
        return records if limit is None else records[:limit]


def test_synthetic_export_discovery_passes_bounded_reads_to_the_store() -> None:
    digest = _digest("synthetic-export")
    store = _SyntheticExportStore(
        (SimpleNamespace(run_id="run-1"),),
        {"run-1": ({"storage_ref": f"artifact://sha256/{digest}", "digest": digest},)},
    )

    assert discover_synthetic_data_artifact_references(store, max_runs=1, max_exports=1) == {
        "synthetic_data_exports": (digest,)
    }
    assert store.snapshot_limit == 2
    assert store.artifact_limits == [2]


def test_synthetic_export_discovery_fails_closed_when_store_ignores_bounds() -> None:
    digest = _digest("synthetic-export")

    class UnboundedSyntheticStore:
        def snapshot(self, *, limit=None):
            assert limit == 2
            return (SimpleNamespace(run_id="run-1"), SimpleNamespace(run_id="run-2"))

        def artifacts(self, run_id: str, *, limit=None):
            del run_id
            assert limit == 2
            return tuple(
                {"storage_ref": f"artifact://sha256/{digest}", "digest": digest} for _ in range(2)
            )

    with pytest.raises(ValueError, match="synthetic export inventory exceeded its run bound"):
        discover_synthetic_data_artifact_references(UnboundedSyntheticStore(), max_runs=1)

    class UnboundedArtifactsStore:
        def snapshot(self, *, limit=None):
            assert limit == 2
            return (SimpleNamespace(run_id="run-1"),)

        def artifacts(self, run_id: str, *, limit=None):
            del run_id
            assert limit == 2
            return tuple(
                {"storage_ref": f"artifact://sha256/{digest}", "digest": digest} for _ in range(2)
            )

    with pytest.raises(ValueError, match="synthetic export inventory exceeded its export bound"):
        discover_synthetic_data_artifact_references(
            UnboundedArtifactsStore(), max_runs=1, max_exports=1
        )


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def test_catalog_discovery_covers_revisions_and_local_file_snapshots() -> None:
    file_digest = _digest("file")
    dataset_digest = _digest("dataset")
    file_asset = CatalogAsset(AssetId("file-a"), "file", "source.csv")
    dataset_asset = CatalogAsset(AssetId("dataset-a"), "dataset", "processed")
    entries = (
        (
            file_asset,
            AssetRevision(
                AssetRef(file_asset.id, AssetVersion("v1")),
                metadata=(("artifact_ref", f"artifact://sha256/{file_digest}"),),
            ),
        ),
        (
            dataset_asset,
            AssetRevision(
                AssetRef(dataset_asset.id, AssetVersion("v1")),
                metadata=(("artifact_ref", f"artifact://sha256/{dataset_digest}"),),
            ),
        ),
    )

    references = discover_catalog_artifact_references(_WorkspaceStore(), _CatalogStore(entries))

    assert references == {
        "catalog_revisions": tuple(sorted((file_digest, dataset_digest))),
        "local_files": (file_digest,),
    }


def test_ml_discovery_checks_run_and_model_artifact_identity() -> None:
    run_digest = _digest("run-artifact")
    runtime_digest = _digest("runtime-snapshot")
    model_digest = _digest("model-artifact")
    run_id = MLRunId("run-a")
    dataset = AssetRef(AssetId("dataset-a"), AssetVersion("v1"))
    run = MLRunRecord(
        id=run_id,
        experiment_id=ExperimentId("experiment-a"),
        execution_ref="execution-a",
        source_revision="revision-a",
        datasets=(dataset,),
        artifact_refs=(f"artifact://sha256/{run_digest}",),
        runtime_snapshot_ref=f"artifact://sha256/{runtime_digest}",
    )
    model = RegisteredModelVersion(
        model_id=ModelId("model-a"),
        version=ModelVersion("1"),
        source_run_id=run_id,
        artifact_ref=f"artifact://sha256/{model_digest}",
        artifact_digest=model_digest,
        framework="scikit-learn",
        signature=ModelSignature((("x", "number"),), (("y", "number"),)),
    )

    references = discover_ml_artifact_references(_WorkspaceStore(), _MLRegistry((run,), (model,)))

    assert references == {
        "ml_runs": tuple(sorted((run_digest, runtime_digest))),
        "registered_models": (model_digest,),
    }


def test_queryflux_evidence_discovery_validates_and_bounds_durable_refs() -> None:
    digest = _digest("query-evidence")
    store = _DataEngineeringQueryEvidenceStore(
        ({"storage_ref": f"artifact://sha256/{digest}", "digest": digest},)
    )
    assert discover_data_engineering_query_evidence_references(store) == {
        "data_engineering_query_evidence": (digest,)
    }

    class UnboundedQueryEvidenceStore:
        def list_evidence_references(self, *, max_references=10_000):
            del max_references
            return ({}, {})

    with pytest.raises(ValueError, match="reference inventory exceeded its bound"):
        discover_data_engineering_query_evidence_references(
            UnboundedQueryEvidenceStore(), max_references=1
        )


def test_discovery_fails_closed_on_invalid_refs_and_incomplete_source_set(
    tmp_path,
) -> None:
    file_asset = CatalogAsset(AssetId("file-b"), "file", "source.csv")
    invalid_entry = (
        file_asset,
        AssetRevision(
            AssetRef(file_asset.id, AssetVersion("v1")),
            metadata=(("artifact_ref", "artifact://sha256/not-a-digest"),),
        ),
    )
    with pytest.raises(ValueError, match="lowercase sha256"):
        discover_catalog_artifact_references(_WorkspaceStore(), _CatalogStore((invalid_entry,)))

    store = LocalArtifactStore(tmp_path / "artifacts")
    store.put_bytes(role="stale", data=b"stale")
    partial = {
        "catalog_revisions": (),
        "local_files": (),
        "ml_runs": (),
        "registered_models": (),
    }
    plan = plan_unreferenced(store, partial)
    assert plan.missing_sources == tuple(sorted(REQUIRED_ARTIFACT_REFERENCE_SOURCES - set(partial)))
    assert plan.candidate_digests == ()


def test_aggregate_discovery_returns_all_known_reference_sources() -> None:
    references = discover_artifact_references(
        _WorkspaceStore(),
        _CatalogStore(()),
        _MLRegistry((), ()),
        _DurableJobStore(()),
        _ConnectorOutputStore(),
        _DataEngineeringRevisionStore(),
        _DataEngineeringQueryEvidenceStore(),
        _SyntheticExportStore(),
    )

    assert set(references) == REQUIRED_ARTIFACT_REFERENCE_SOURCES
    assert all(not digests for digests in references.values())


class _DurableJobStore:
    def __init__(
        self,
        records: tuple[tuple[str, object, tuple[object, ...]], ...],
        historical_runs: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.records = records
        self.historical_runs = historical_runs or {}
        self.run_records = {job_id: (evidence, cells) for job_id, evidence, cells in records}

    def list_jobs(self, *, project_id, project_ids, state, limit, cursor):
        del project_id, project_ids, state, limit
        index = 0 if cursor is None else int(cursor)
        if index >= len(self.records):
            return SimpleNamespace(items=(), next_cursor=None)
        job_id, evidence, cells = self.records[index]
        return SimpleNamespace(
            items=(SimpleNamespace(id=job_id),),
            next_cursor=str(index + 1) if index + 1 < len(self.records) else None,
        )

    def get_run_id_for_job(self, job_id):
        return job_id

    def list_run_ids_for_job(self, job_id):
        return (job_id, *self.historical_runs.get(job_id, ()))

    def read_evidence(self, run_id):
        return self.run_records[run_id][0]

    def read_evidence_bounded(self, run_id, *, limit):
        return self.run_records[run_id][0][: limit + 1]

    def read_cell_results(self, run_id):
        return self.run_records[run_id][1]

    def read_cell_results_bounded(self, run_id, *, limit):
        return self.run_records[run_id][1][: limit + 1]


def test_durable_discovery_pages_jobs_and_separates_execution_and_checkpoint_refs() -> None:
    execution_digest = _digest("durable-evidence")
    checkpoint_digest = _digest("durable-checkpoint")
    result = SimpleNamespace(
        result_json=json.dumps(
            {
                "artifact": {
                    "role": "ml-node-checkpoint",
                    "digest": checkpoint_digest,
                    "storage_ref": f"artifact://sha256/{checkpoint_digest}",
                }
            }
        )
    )
    evidence = SimpleNamespace(
        availability=EvidenceAvailability.AVAILABLE,
        digest=execution_digest,
        storage_ref=f"artifact://sha256/{execution_digest}",
    )
    store = _DurableJobStore((("0", (evidence,), (result,)), ("1", (), ())))

    references = discover_durable_job_artifact_references(store, page_size=1)

    assert references == {
        "durable_execution_results": (execution_digest,),
        "durable_job_checkpoints": (checkpoint_digest,),
    }


def test_durable_discovery_fails_closed_on_malformed_artifact_locator() -> None:
    result = SimpleNamespace(
        result_json=json.dumps({"artifact": {"digest": _digest("broken"), "storage_ref": "bad"}})
    )
    store = _DurableJobStore((("0", (), (result,)),))

    with pytest.raises(ValueError, match="artifact://sha256"):
        discover_durable_job_artifact_references(store)


def test_durable_discovery_includes_references_from_historical_runs() -> None:
    old_digest = _digest("old-run-evidence")
    old_evidence = SimpleNamespace(
        availability=EvidenceAvailability.AVAILABLE,
        digest=old_digest,
        storage_ref=f"artifact://sha256/{old_digest}",
    )
    store = _DurableJobStore(
        (("0", (), ()),),
        historical_runs={"0": ("old-run",)},
    )
    store.run_records["old-run"] = ((old_evidence,), ())

    references = discover_durable_job_artifact_references(store)

    assert references["durable_execution_results"] == (old_digest,)


def test_durable_discovery_fails_closed_when_job_inventory_exceeds_bound() -> None:
    store = _DurableJobStore((("0", (), ()), ("1", (), ())))

    with pytest.raises(ValueError, match="page bound"):
        discover_durable_job_artifact_references(store, page_size=1, max_pages=1)

    with pytest.raises(ValueError, match="run bound"):
        discover_durable_job_artifact_references(
            _DurableJobStore((("0", (), ()),), historical_runs={"0": ("old-run",)}),
            max_runs=1,
        )


def test_durable_discovery_fails_closed_when_cell_results_exceed_bounds() -> None:
    store = _DurableJobStore((("0", (), (SimpleNamespace(result_json="{}"),) * 2),))

    with pytest.raises(ValueError, match="cell results exceeded their reference bound"):
        discover_durable_job_artifact_references(store, max_cell_results_per_run=1)

    with pytest.raises(ValueError, match="cell results exceeded their reference bound"):
        discover_durable_job_artifact_references(store, max_cell_results=1)


def test_durable_discovery_fails_closed_when_evidence_exceeds_bounds() -> None:
    digest = _digest("bounded-evidence")
    evidence = SimpleNamespace(
        availability=EvidenceAvailability.AVAILABLE,
        digest=digest,
        storage_ref=f"artifact://sha256/{digest}",
    )
    store = _DurableJobStore((("0", (evidence, evidence), ()),))

    with pytest.raises(ValueError, match="evidence exceeded its reference bound"):
        discover_durable_job_artifact_references(store, max_evidence_refs_per_run=1)


def test_guarded_collection_holds_collector_lease_through_deletion(tmp_path, monkeypatch) -> None:
    live = _digest("still-live")
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.put_bytes(role="live", data=b"still-live")
    stale = store.put_bytes(role="stale", data=b"stale")
    file_asset = CatalogAsset(AssetId("file"), "file", "source.csv")
    catalog = _CatalogStore(
        (
            (
                file_asset,
                AssetRevision(
                    AssetRef(file_asset.id, AssetVersion("v1")),
                    metadata=(("artifact_ref", f"artifact://sha256/{live}"),),
                ),
            ),
        )
    )
    events: list[str] = []

    class Barrier:
        @contextmanager
        def writer(self):
            yield

        @contextmanager
        def collector(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

    original_delete = store.delete

    def delete(ref):
        events.append("delete")
        return original_delete(ref)

    monkeypatch.setattr(store, "delete", delete)
    deleted = collect_referenced_artifacts(
        Barrier(),
        store,
        _WorkspaceStore(),
        catalog,
        _MLRegistry((), ()),
        _DurableJobStore(()),
        _ConnectorOutputStore(),
        _DataEngineeringRevisionStore(),
        _DataEngineeringQueryEvidenceStore(),
        _SyntheticExportStore(),
    )

    assert deleted == (stale.digest,)
    assert events == ["lock", "delete", "unlock"]
    assert store.verify(stale) is False


def test_guarded_collection_releases_lease_without_deleting_on_incomplete_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    stale = store.put_bytes(role="stale", data=b"stale")
    events: list[str] = []

    class Barrier:
        @contextmanager
        def writer(self):
            yield

        @contextmanager
        def collector(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

    def fail_snapshot(_self, *, limit=None):
        del limit
        raise ValueError("synthetic export inventory unavailable")

    monkeypatch.setattr(_SyntheticExportStore, "snapshot", fail_snapshot)
    with pytest.raises(ValueError, match="inventory unavailable"):
        collect_referenced_artifacts(
            Barrier(),
            store,
            _WorkspaceStore(),
            _CatalogStore(()),
            _MLRegistry((), ()),
            _DurableJobStore(()),
            _ConnectorOutputStore(),
            _DataEngineeringRevisionStore(),
            _DataEngineeringQueryEvidenceStore(),
            _SyntheticExportStore(),
        )

    assert events == ["lock", "unlock"]
    assert store.get_bytes_by_storage_ref(stale.storage_ref, digest=stale.digest) == b"stale"
