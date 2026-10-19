from __future__ import annotations

import asyncio
import csv
import time
from types import SimpleNamespace

import pytest
from studio_cli.local_composed import _workflow_reader_for_backend, build_local_composed_from_env
from studio_core import AssetId, ConnectionDefinition, ConnectionId, WorkspaceId
from studio_core.canonical_json import decode as decode_canonical_json
from studio_execution import PostgresWorkflowHTTPAdapter, SqliteWorkflowHTTPAdapter
from studio_ml import FeatureSpec, Lab
from studio_ml.domain import PipelineIR
from studio_ml.orchestration import JobStoreExecutionStore
from studio_orchestrator import Instant
from studio_server import LocalServerComposition
from studio_storage import (
    ArtifactRef,
    LocalArtifactStore,
    PostgresSchedulerSnapshotStore,
    SqliteCatalogStore,
)
from studio_storage.local_files import LocalFileConnector


def _environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        (
            '{"version": 1, "grants": [{"actions": ['
            '"cancel", "evidence:read", "execute", "events", "list", "read", "submit"'
            '], "constraints": {}, "resource": '
            '{"identifier": null, "kind": "*"}, "version": 1}]}'
        ),
    )
    monkeypatch.setenv("RONIN_TOKEN", "job-token")


def test_workflow_routes_are_not_mounted_for_incomplete_postgres_scheduler_store() -> None:
    assert (
        _workflow_reader_for_backend(
            object(),
            now=Instant("2026-10-17T00:00:00.000000Z"),
            postgres_dsn="postgresql://localhost/ronin",
        )
        is None
    )


def test_workflow_routes_mount_for_complete_postgres_scheduler_store() -> None:
    store = object.__new__(PostgresSchedulerSnapshotStore)
    reader = _workflow_reader_for_backend(
        store,
        now=Instant("2026-10-17T00:00:00.000000Z"),
        postgres_dsn="postgresql://localhost/ronin",
    )
    assert isinstance(reader, PostgresWorkflowHTTPAdapter)


def test_workflow_routes_use_the_complete_sqlite_scheduler_contract(tmp_path) -> None:
    from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore

    store = SqliteWorkflowBundleImportStore(
        tmp_path / "scheduler.sqlite3", migration_now="2026-10-17T00:00:00.000000Z"
    )
    reader = _workflow_reader_for_backend(
        store, now=Instant("2026-10-17T00:00:00.000000Z"), postgres_dsn=None
    )
    assert isinstance(reader, SqliteWorkflowHTTPAdapter)


def test_build_local_composed_from_env_creates_two_surface_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)

    composition = build_local_composed_from_env()

    assert isinstance(composition, LocalServerComposition)
    assert composition.job_server.server_address[1] == 8080
    assert composition.control_plane_server.server_address[1] == 8081
    assert composition.plugin_host is not None
    assert composition.control_plane_server.data_engineering_reader is not None
    assert composition.control_plane_server.connector_registry is not None
    assert composition.control_plane_server.ingestion_adapter is not None
    workspace = composition.control_plane_server.workspace_service.get(WorkspaceId("workspace-1"))
    assert workspace.name == "Local workspace"
    assert composition.control_plane_server.plugin_routes_enabled
    composition.stop()


def test_local_composition_injects_the_shared_durable_job_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    composition = build_local_composed_from_env()
    assert composition.plugin_host is not None
    assert composition.plugin_host.plan is not None
    ml_plugin = next(
        record.plugin
        for record in composition.plugin_host.plan.records
        if record.manifest.id == "com.sauronshepherd.ronin.ml-studio"
    )
    try:
        assert isinstance(ml_plugin._coordinator._store, JobStoreExecutionStore)
        assert isinstance(ml_plugin._dataset_resolver._catalog, SqliteCatalogStore)
        assert isinstance(ml_plugin._dataset_resolver._artifacts, LocalArtifactStore)
        assert ml_plugin._coordinator._store._artifact_store is ml_plugin._artifacts
    finally:
        composition.stop()


def test_local_composition_queues_large_assetref_input_as_verified_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    composition = build_local_composed_from_env()
    assert composition.plugin_host is not None
    assert composition.plugin_host.plan is not None
    ml_plugin = next(
        record.plugin
        for record in composition.plugin_host.plan.records
        if record.manifest.id == "com.sauronshepherd.ronin.ml-studio"
    )
    try:
        source_root = tmp_path / "source"
        source_root.mkdir()
        source_path = source_root / "large.csv"
        payload = "p" * 55_000
        with source_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("x", "target", "payload"))
            writer.writerows((number, number % 2, payload) for number in range(20))
        assert source_path.stat().st_size > 1_048_576

        artifact_store = ml_plugin._artifacts
        catalog_store = ml_plugin._dataset_resolver._catalog
        assert isinstance(artifact_store, LocalArtifactStore)
        assert isinstance(catalog_store, SqliteCatalogStore)
        ingestion = LocalFileConnector(source_root).ingest(
            workspace_id=WorkspaceId("workspace-1"),
            connection=ConnectionDefinition(
                ConnectionId("local-files"), "Local files", "ronin.local-file"
            ),
            relative_path="large.csv",
            target_asset_id=AssetId("large-dataset"),
            target_name="Large dataset",
            artifact_store=artifact_store,
            catalog_store=catalog_store,
            now=Instant("2026-10-19T00:00:00.000000Z"),
        )
        lab = Lab(
            "large-async-lab",
            "Large async lab",
            "project-1",
            ingestion.target,
            "target",
            "classification",
            (FeatureSpec("x", "numeric"),),
        )
        ml_plugin._labs.create(WorkspaceId("workspace-1"), lab)

        class CapturingRunner:
            def run(self, _lab, rows):
                return SimpleNamespace(
                    to_payload=lambda: {
                        "row_count": len(rows),
                        "payload_chars": len(rows[0]["payload"]),
                    }
                )

        ml_plugin._coordinator._runner = CapturingRunner()
        composition.plugin_host.start()
        submitted = ml_plugin.submit_execution(
            "workspace-1", lab.id, body={"run_id": "large-assetref-run"}
        )
        assert submitted["run_id"] == "large-assetref-run"
        deadline = time.monotonic() + 10
        status = ml_plugin.execution_status("large-assetref-run", workspace_id="workspace-1")
        while status["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
            time.sleep(0.01)
            status = ml_plugin.execution_status("large-assetref-run", workspace_id="workspace-1")
        assert status["state"] == "succeeded"
        assert status["result"] == {"row_count": 20, "payload_chars": 55_000}

        execution_store = ml_plugin._coordinator._store
        job_id, _run_id = execution_store._ids("workspace-1", "large-assetref-run")
        job = asyncio.run(execution_store._service.status(job_id))
        assert job is not None
        parameters = decode_canonical_json(job.parameters_json)
        assert isinstance(parameters, dict)
        assert parameters["schema"] == "ronin.ml-execution.v2"
        assert isinstance(parameters["pipeline_json"], str)
        pipeline = PipelineIR.from_json(parameters["pipeline_json"])
        assert parameters["pipeline_digest"] == pipeline.digest
        assert dict(pipeline.parameters)["lab_digest"] == lab.digest
        assert parameters["request_digest"] == job.request_digest
        assert parameters["rows_json"] is None
        assert isinstance(parameters["rows_artifact"], dict)
        assert len(job.parameters_json.encode("utf-8")) < 10_000
        input_ref = ArtifactRef(**parameters["rows_artifact"])
        assert artifact_store.verify(input_ref)
    finally:
        composition.stop()


def test_build_local_composed_rejects_unknown_permission(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PERMISSIONS", "workspace.read,unknown")

    with pytest.raises(ValueError, match="unsupported permissions"):
        build_local_composed_from_env()


def test_build_local_composed_rejects_invalid_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_PORT", "0")

    with pytest.raises(ValueError, match="between 1 and 65535"):
        build_local_composed_from_env()


def test_build_local_composed_accepts_explicit_legacy_plugin_rollout(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_PLUGIN_API", "legacy")

    composition = build_local_composed_from_env()

    assert not composition.control_plane_server.plugin_routes_enabled
    composition.stop()


def test_build_local_composed_accepts_workspace_write_permission(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS", "workspace.read,workspace.write,project.read"
    )

    composition = build_local_composed_from_env()

    assert composition.control_plane_server is not None
    composition.stop()


def test_build_local_composed_rejects_unknown_plugin_rollout(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_PLUGIN_API", "unknown")

    with pytest.raises(ValueError, match="RONIN_PLUGIN_API"):
        build_local_composed_from_env()


def test_build_local_composed_validates_configured_plugin_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    from studio_runtime import PluginHost

    lock_path = tmp_path / "plugin-lock.json"
    lock_path.write_text(PluginHost.discover().create_lock().dumps(), encoding="utf-8")
    monkeypatch.setenv("RONIN_PLUGIN_LOCK", str(lock_path))

    composition = build_local_composed_from_env()

    assert composition.plugin_host is not None
    composition.stop()


def test_build_local_composed_rejects_invalid_configured_plugin_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    lock_path = tmp_path / "plugin-lock.json"
    lock_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("RONIN_PLUGIN_LOCK", str(lock_path))

    with pytest.raises(ValueError, match="RONIN_PLUGIN_LOCK validation failed"):
        build_local_composed_from_env()
