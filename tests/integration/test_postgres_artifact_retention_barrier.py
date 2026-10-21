from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
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
from studio_data_engineering import PostgresQueryEvidenceReferenceStore
from studio_storage import (
    LocalArtifactStore,
    PostgresArtifactReferenceBarrier,
    collect_referenced_artifacts,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL retention barrier qualification requires RONIN_POSTGRES_TEST_DSN",
)


def test_collector_waits_for_writers_and_fences_new_writers() -> None:
    barrier = PostgresArtifactReferenceBarrier(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-retention-barrier-qualification",
    )
    writer_entered = Event()
    release_writer = Event()
    collector_entered = Event()
    writer_blocked_by_collector = Event()
    release_collector = Event()

    def write() -> None:
        with barrier.writer():
            writer_entered.set()
            assert release_writer.wait(timeout=10)

    def collect() -> None:
        with barrier.collector():
            collector_entered.set()
            assert release_collector.wait(timeout=10)

    def second_write() -> None:
        with barrier.writer():
            writer_blocked_by_collector.set()

    with ThreadPoolExecutor(max_workers=3) as executor:
        writer_future = executor.submit(write)
        assert writer_entered.wait(timeout=5)
        collector_future = executor.submit(collect)
        assert not collector_entered.wait(timeout=0.25)
        release_writer.set()
        writer_future.result(timeout=5)
        assert collector_entered.wait(timeout=5)

        second_writer_future = executor.submit(second_write)
        assert not writer_blocked_by_collector.wait(timeout=0.25)
        release_collector.set()
        collector_future.result(timeout=5)
        second_writer_future.result(timeout=5)
        assert writer_blocked_by_collector.is_set()


def test_async_worker_writer_blocks_collector_until_reference_commit() -> None:
    barrier = PostgresArtifactReferenceBarrier(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-async-worker-barrier-qualification",
    )
    collector_entered = Event()
    release_collector = Event()

    def collect() -> None:
        with barrier.collector():
            collector_entered.set()
            assert release_collector.wait(timeout=10)

    async def exercise() -> None:
        with ThreadPoolExecutor(max_workers=1) as executor:
            async with barrier.awriter():
                collector_future = executor.submit(collect)
                assert not await asyncio.to_thread(collector_entered.wait, 0.25)
            assert await asyncio.to_thread(collector_entered.wait, 5)
            release_collector.set()
            await asyncio.to_thread(collector_future.result, 5)

    asyncio.run(exercise())


def test_bounded_reference_collection_uses_real_postgres_collector_lease(tmp_path) -> None:
    barrier = PostgresArtifactReferenceBarrier(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-retention-collector-qualification",
    )
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    live = artifacts.put_bytes(role="live", data=b"live")
    query_evidence = artifacts.put_bytes(role="query-evidence", data=b"query-evidence")
    stale = artifacts.put_bytes(role="stale", data=b"stale")
    query_evidence_store = PostgresQueryEvidenceReferenceStore(
        os.environ["RONIN_POSTGRES_TEST_DSN"],
        application_name="ronin-retention-query-evidence-qualification",
    )
    with barrier.writer():
        query_evidence_store.record(
            project_id="retention-project",
            run_id="retention-run",
            attempt_id="retention-attempt",
            artifact=query_evidence,
        )
    workspace = Workspace(WorkspaceId("retention-workspace"), "Retention")
    file_asset = CatalogAsset(AssetId("source-file"), "file", "source.csv")
    revision = AssetRevision(
        AssetRef(file_asset.id, AssetVersion("v1")),
        metadata=(("artifact_ref", live.storage_ref),),
    )

    class Workspaces:
        def list_workspaces(self, *, limit=None):
            del limit
            return (workspace,)

    class Catalog:
        def list_assets(self, workspace_id, *, limit=None):
            assert workspace_id == workspace.id
            del limit
            return (file_asset,)

        def list_revisions(self, workspace_id, asset_id, *, limit=None):
            assert workspace_id == workspace.id
            del limit
            return (revision,) if asset_id == file_asset.id else ()

    class MLRegistry:
        def list_runs(self, workspace_id, *, limit=None):
            del workspace_id, limit
            return ()

        def list_models(self, workspace_id, *, limit=None):
            del workspace_id, limit
            return ()

    class Jobs:
        def list_jobs(self, **_kwargs):
            return SimpleNamespace(items=(), next_cursor=None)

        def read_evidence_bounded(self, run_id, *, limit):
            del run_id, limit
            return ()

        def read_cell_results_bounded(self, run_id, *, limit):
            del run_id, limit
            return ()

    class ConnectorCheckpoints:
        def list_committed_outputs(self, *, max_outputs=10_000):
            del max_outputs
            return ()

    class Revisions:
        def list_all_revisions(self, *, max_revisions=10_000):
            del max_revisions
            return ()

    class SyntheticExports:
        def snapshot(self):
            return ()

        def artifacts(self, run_id):
            del run_id
            return ()

    deleted = collect_referenced_artifacts(
        barrier,
        artifacts,
        Workspaces(),
        Catalog(),
        MLRegistry(),
        Jobs(),
        ConnectorCheckpoints(),
        Revisions(),
        query_evidence_store,
        SyntheticExports(),
    )

    assert deleted == (stale.digest,)
    assert artifacts.verify(live)
    assert artifacts.verify(query_evidence)
    assert not artifacts.verify(stale)
