from __future__ import annotations

import asyncio
import csv
import http.client
import json
import socket
import time
from types import SimpleNamespace

import pytest
from studio_cli.local_composed import (
    _catalog_reader_for_backend,
    _workflow_reader_for_backend,
    build_local_composed_from_env,
)
from studio_core import (
    AssetId,
    ConnectionDefinition,
    ConnectionId,
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    WorkspaceId,
)
from studio_core.canonical_json import decode as decode_canonical_json
from studio_execution import PostgresWorkflowHTTPAdapter, SqliteWorkflowHTTPAdapter
from studio_lakehouse import write_parquet_rows
from studio_ml import FeatureSpec, Lab
from studio_ml.domain import PipelineIR
from studio_ml.orchestration import JobStoreExecutionStore
from studio_orchestrator import Instant
from studio_server import LocalServerComposition
from studio_sql import SqlExplainUnsupportedError, SqlTimeoutError
from studio_storage import (
    ArtifactRef,
    LocalArtifactStore,
    PostgresSchedulerSnapshotStore,
    SqliteAuditStore,
    SqliteCatalogStore,
)
from studio_storage.local_files import LocalFileConnector
from studio_synthetic_data import ColumnSpec, GenerationPlan, TableSpec
from studio_synthetic_data.application import GovernStudioService, SqliteRunStore


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


def _unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _sql_request(
    address: tuple[str, int], project_id: str, sql: str, **limits: int
) -> tuple[int, object]:
    connection = http.client.HTTPConnection(*address, timeout=5)
    body = json.dumps({"sql": sql, **limits}, separators=(",", ":"))
    try:
        connection.request(
            "POST",
            f"/v1/workspaces/workspace-1/projects/{project_id}/sql/query",
            body=body,
            headers={
                "Authorization": "Bearer control-token",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _sql_explain_request(
    address: tuple[str, int], project_id: str, sql: str, **limits: object
) -> tuple[int, object]:
    connection = http.client.HTTPConnection(*address, timeout=5)
    body = json.dumps({"sql": sql, **limits}, separators=(",", ":"))
    try:
        connection.request(
            "POST",
            f"/v1/workspaces/workspace-1/projects/{project_id}/sql/explain",
            body=body,
            headers={
                "Authorization": "Bearer control-token",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


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


def test_workflow_routes_are_not_mounted_for_incomplete_sqlite_scheduler_store(tmp_path) -> None:
    from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore

    store = SqliteWorkflowBundleImportStore(
        tmp_path / "scheduler.sqlite3", migration_now="2026-10-17T00:00:00.000000Z"
    )
    assert (
        _workflow_reader_for_backend(
            store, now=Instant("2026-10-17T00:00:00.000000Z"), postgres_dsn=None
        )
        is None
    )


def test_workflow_routes_mount_for_complete_sqlite_scheduler_contract(tmp_path) -> None:
    from studio_storage.scheduler_backfill import SchedulerBackfillStore

    store = SchedulerBackfillStore(
        tmp_path / "scheduler.sqlite3", migration_now="2026-10-17T00:00:00.000000Z"
    )
    reader = _workflow_reader_for_backend(
        store, now=Instant("2026-10-17T00:00:00.000000Z"), postgres_dsn=None
    )
    assert isinstance(reader, SqliteWorkflowHTTPAdapter)


def test_catalog_routes_require_the_complete_store_contract(tmp_path) -> None:
    complete = object.__new__(PostgresSchedulerSnapshotStore)
    assert _catalog_reader_for_backend(complete) is complete
    assert (
        _catalog_reader_for_backend(SimpleNamespace(list_assets=lambda *_args, **_kwargs: ()))
        is None
    )

    sqlite_store = SqliteCatalogStore(
        tmp_path / "catalog.sqlite3", migration_now="2026-10-17T00:00:00.000000Z"
    )
    assert _catalog_reader_for_backend(sqlite_store) is sqlite_store


def test_build_local_composed_from_env_creates_two_surface_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)

    composition = build_local_composed_from_env()

    assert isinstance(composition, LocalServerComposition)
    assert composition.job_server.server_address[1] == 8080
    assert composition.control_plane_server.server_address[1] == 8081
    assert composition.plugin_host is not None
    assert composition.plugin_host.plan is not None
    plugin_ids = {record.manifest.id for record in composition.plugin_host.plan.records}
    assert "com.sauronshepherd.ronin.ai-studio" not in plugin_ids
    assert "com.sauronshepherd.ronin.genai" not in plugin_ids
    assert composition.control_plane_server.data_engineering_reader is not None
    assert composition.control_plane_server.connector_registry is not None
    assert composition.control_plane_server.ingestion_adapter is not None
    assert composition.control_plane_server.durable_jobs is composition.job_server.application
    assert composition.control_plane_server.alert_reader is not None
    assert composition.control_plane_server.streaming_health_reader is not None
    assert composition.control_plane_server.streaming_runner is not None
    assert composition.control_plane_server.workflow_reader is not None
    assert (
        composition.control_plane_server.workflow_runner
        is composition.control_plane_server.workflow_reader
    )
    assert composition.control_plane_server.workflow_canceller is not None
    workspace = composition.control_plane_server.workspace_service.get(WorkspaceId("workspace-1"))
    assert workspace.name == "Local workspace"
    assert composition.control_plane_server.plugin_routes_enabled
    composition.stop()


def test_local_composed_persists_project_mutations_to_the_audit_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PLUGIN_API", "legacy")
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "workspace.read,workspace.write,project.read,project.write",
    )
    composition = build_local_composed_from_env()
    audit_store = SqliteAuditStore(
        tmp_path / "ronin.sqlite3", migration_now=Instant("2026-10-17T00:00:00.000000Z")
    )
    manifest = ProjectManifest.from_project(
        Project(
            ProjectId("audit-project"),
            "Audit project",
            (RepositoryBinding("code", "https://example.test/repo.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )
    server = composition.control_plane_server
    try:
        composition.start()
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        try:
            connection.request(
                "POST",
                "/v1/workspaces/workspace-1/projects",
                body=json.dumps(manifest.to_data()).encode("utf-8"),
                headers={
                    "Authorization": "Bearer control-token",
                    "Content-Type": "application/json",
                    "Idempotency-Key": "audit-project-create",
                },
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

        assert response.status in {200, 201}, payload
        events = audit_store.list_for_resource(
            WorkspaceId("workspace-1"),
            resource_kind="workspace_resource",
            resource_ref="workspace-1/audit-project",
        )
        assert len(events) == 1
        assert events[0].action == "project.register"
        assert events[0].outcome == "succeeded"
        assert events[0].actor.ref
    finally:
        composition.stop()


def test_local_composed_data_engineering_health_and_debugger_routes_are_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    composition = build_local_composed_from_env()
    server = composition.control_plane_server
    assert composition.plugin_host is not None
    assert composition.plugin_host.resolve_route("GET", "/v1/data-engineering/health") is not None

    def request(method: str, path: str, body: object | None = None) -> tuple[int, object]:
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": "Bearer control-token"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    try:
        composition.start()
        health_status, health = request(
            "GET", "/v1/data-engineering/health?workspace_id=workspace-1"
        )
        assert health_status == 200, health
        assert health["status"] == "ready"

        missing_stream_status, missing_stream = request(
            "GET", "/v1/workspaces/workspace-1/streams/not-configured/health"
        )
        assert missing_stream_status == 404, missing_stream
        assert missing_stream["error"]["code"] == "not_found"

        create_status, created = request(
            "POST",
            "/v1/data-engineering/debugger/sessions?workspace_id=workspace-1",
            {
                "session_id": "local-composed-debug",
                "cells": [{"cell_id": "cell-1", "source": "SELECT 1"}],
            },
        )
        assert create_status == 200, created
        assert created["session_id"] == "local-composed-debug"
        assert created["cells"][0]["cell_id"] == "cell-1"

        breakpoint_status, breakpoint = request(
            "POST",
            "/v1/data-engineering/debugger/sessions/local-composed-debug/breakpoints/cell-1?workspace_id=workspace-1",
            {},
        )
        assert breakpoint_status == 200, breakpoint
        assert breakpoint["cells"][0]["breakpoint"] is True
    finally:
        composition.stop()


def test_local_composed_sql_route_executes_scoped_queries_and_closes_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    composition = build_local_composed_from_env()
    server = composition.control_plane_server
    sql_reader = server.sql_reader
    assert sql_reader is not None
    engine = sql_reader._engine
    server.project_service.register(
        WorkspaceId("workspace-1"),
        ProjectManifest.from_project(
            Project(
                ProjectId("project-1"),
                "SQL test project",
                (RepositoryBinding("code", "https://example.test/repo.git", role="primary"),),
                ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
            )
        ),
        now=Instant("2026-10-26T00:00:00.000000Z"),
    )
    try:
        composition.start()
        status, missing = _sql_request(server.server_address, "missing-project", "SELECT 1")
        assert status == 404
        assert missing["error"]["code"] == "not_found"
        assert engine._engines == {}

        status, result = _sql_request(
            server.server_address,
            "project-1",
            "SELECT 1 AS value UNION ALL SELECT 2 AS value",
        )
        assert status == 200
        assert result["rows"] == [[1], [2]]
        assert result["row_count"] == 2

        parquet_path = tmp_path / "registered-events.parquet"
        write_parquet_rows(parquet_path, ({"id": 1}, {"id": 2}))
        from studio_semantic import semantic_project_scope

        engine.register_parquet(
            semantic_project_scope("workspace-1", "project-1"),
            "registered_events",
            str(parquet_path),
        )
        status, explained = _sql_explain_request(
            server.server_address,
            "project-1",
            "SELECT id FROM registered_events WHERE id = ?",
            parameters=[2],
        )
        assert status == 200
        assert explained["rows"]
        assert explained["max_bytes"] == 262_144
        assert str(parquet_path) not in json.dumps(explained)

        status, unavailable_explain = _sql_explain_request(
            server.server_address, "project-1", "SELECT * FROM not_registered"
        )
        assert status == 404
        assert unavailable_explain["error"]["code"] == "sql_relation_unavailable"
        status, unavailable_query = _sql_request(
            server.server_address, "project-1", "SELECT * FROM not_registered"
        )
        assert status == 404
        assert unavailable_query["error"]["code"] == "sql_relation_unavailable"

        status, explain_too_large = _sql_explain_request(
            server.server_address,
            "project-1",
            "SELECT id FROM registered_events",
            max_bytes=1,
        )
        assert status == 413
        assert explain_too_large["error"]["code"] == "sql_result_too_large"

        status, typed = _sql_request(
            server.server_address, "project-1", "SELECT CAST(12.34 AS DECIMAL(5, 2)) AS amount"
        )
        assert status == 200
        assert typed["rows"] == [["12.34"]]

        status, oversized = _sql_request(
            server.server_address,
            "project-1",
            "SELECT REPEAT('x', 512)",
            max_result_bytes=128,
        )
        assert status == 413
        assert oversized["error"]["code"] == "sql_result_too_large"

        original_reader = server.sql_reader

        class TimedOutSqlReader:
            def query(self, _project_id: str, _body: object) -> dict[str, object]:
                raise SqlTimeoutError("SQL query exceeded its execution time limit")

            def explain(self, _project_id: str, _body: object) -> dict[str, object]:
                raise SqlTimeoutError("SQL query exceeded its execution time limit")

            def close(self) -> None:
                return None

        server.sql_reader = TimedOutSqlReader()
        try:
            status, timed_out = _sql_request(server.server_address, "project-1", "SELECT 1")
            assert status == 408
            assert timed_out["error"]["code"] == "sql_timeout"
            assert timed_out["error"]["message"] == "SQL query exceeded its execution time limit"
        finally:
            server.sql_reader = original_reader

        class UnsupportedSqlReader:
            def query(self, _project_id: str, _body: object) -> dict[str, object]:
                return {}

            def explain(self, _project_id: str, _body: object) -> dict[str, object]:
                raise SqlExplainUnsupportedError("unsupported")

            def close(self) -> None:
                return None

        server.sql_reader = UnsupportedSqlReader()
        try:
            status, unsupported = _sql_explain_request(
                server.server_address, "project-1", "SELECT 1"
            )
            assert status == 501
            assert unsupported["error"]["code"] == "sql_explain_unsupported"
        finally:
            server.sql_reader = original_reader
    finally:
        composition.stop()
    assert engine._closed


def test_local_composed_migration_route_is_authenticated_and_persists_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    path = "/v1/workspaces/workspace-1/projects/project-1/migration/sessions"
    composition = build_local_composed_from_env()
    try:
        composition.start()
        connection = http.client.HTTPConnection(*composition.job_server.server_address, timeout=5)
        connection.request(
            "POST",
            path,
            body="{}",
            headers={"Authorization": "Bearer job-token", "Content-Type": "application/json"},
        )
        created_response = connection.getresponse()
        created = json.loads(created_response.read().decode("utf-8"))
        connection.close()
        assert created_response.status == 201, created
        assert created["workspace_id"] == "workspace-1"

        composition.stop()
        restarted = build_local_composed_from_env()
        try:
            restarted.start()
            connection = http.client.HTTPConnection(*restarted.job_server.server_address, timeout=5)
            connection.request("GET", path, headers={"Authorization": "Bearer job-token"})
            listed_response = connection.getresponse()
            listed = json.loads(listed_response.read().decode("utf-8"))
            connection.close()
            assert listed_response.status == 200, listed
            assert [item["id"] for item in listed["items"]] == [created["id"]]
        finally:
            restarted.stop()
    finally:
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


def test_local_composition_persists_synthetic_export_references_across_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    composition = build_local_composed_from_env()
    assert composition.plugin_host is not None
    assert composition.plugin_host.plan is not None
    plugin = next(
        record.plugin
        for record in composition.plugin_host.plan.records
        if record.manifest.id == "com.ronin.synthetic-data-studio"
    )
    plan = GenerationPlan(
        (
            TableSpec(
                "customers",
                (ColumnSpec("customer_id", kind="integer", nullable=False),),
                primary_key="customer_id",
                rows=2,
            ),
        ),
        seed=7,
    )
    try:
        assert isinstance(plugin.service, GovernStudioService)
        assert isinstance(plugin.service._store, SqliteRunStore)
        generated = plugin.generate(body={"plan": plan}, idempotency_key="retention-run")
        run_id = generated["run_id"]
        exported = plugin.export(body={"run_id": run_id, "format_id": "csv", "table": "customers"})
        assert exported["artifact"]["storage_ref"].startswith("artifact://sha256/")
        digest = exported["artifact"]["digest"]
    finally:
        composition.stop()

    restarted = build_local_composed_from_env()
    assert restarted.plugin_host is not None
    assert restarted.plugin_host.plan is not None
    plugin_after_restart = next(
        record.plugin
        for record in restarted.plugin_host.plan.records
        if record.manifest.id == "com.ronin.synthetic-data-studio"
    )
    try:
        assert plugin_after_restart.service.get_run(run_id).result is not None
        artifact = plugin_after_restart.service.artifacts(run_id)[0]
        assert artifact["digest"] == digest
        assert plugin_after_restart.artifact_store.get_bytes_by_storage_ref(
            artifact["storage_ref"], digest=digest
        )
        assert plugin_after_restart.list_runs()["items"][0]["run_id"] == run_id
    finally:
        restarted.stop()


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
    lock_path.write_text(
        PluginHost.discover(
            excluded_plugin_ids=frozenset(
                {"com.sauronshepherd.ronin.ai-studio", "com.sauronshepherd.ronin.genai"}
            )
        )
        .create_lock()
        .dumps(),
        encoding="utf-8",
    )
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
