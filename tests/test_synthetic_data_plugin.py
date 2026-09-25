import time

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
from studio_core.plugins import ContributionRegistry, PluginContext, PluginManager, PluginRecord
from studio_orchestrator import Instant
from studio_runtime import PluginHost
from studio_storage.artifacts import LocalArtifactStore
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore
from studio_synthetic_data import ColumnSpec, GenerationPlan, TableSpec
from studio_synthetic_data.application import GovernStudioService, SqliteRunStore
from studio_synthetic_data.local_catalogs import resolve_local_identifier
from studio_synthetic_data.plugin import SyntheticDataStudioPlugin


def _plan() -> GenerationPlan:
    return GenerationPlan(
        (
            TableSpec(
                "customers",
                (
                    ColumnSpec("customer_id", kind="integer", nullable=False),
                    ColumnSpec("email", kind="email", nullable=False),
                ),
                primary_key="customer_id",
                rows=3,
            ),
        ),
        seed=7,
    )


def _plugin(
    service: GovernStudioService | None = None, artifact_store=None
) -> SyntheticDataStudioPlugin:
    plugin = SyntheticDataStudioPlugin(service, artifact_store)
    contributions = ContributionRegistry()
    for permission in plugin.manifest.permissions:
        contributions.add_permission(permission, plugin.manifest.id)
    plugin.register(PluginContext(plugin.manifest.id, contributions, {}))
    plugin.startup()
    return plugin


def test_manifest_and_routes_use_synthetic_data_studio_identity() -> None:
    plugin = _plugin()
    assert plugin.manifest.name == "Synthetic Data Studio"
    assert plugin.manifest.id == "com.ronin.synthetic-data-studio"


def test_catalog_provider_profiles_are_local_only() -> None:
    response = _plugin().catalog_providers()
    assert response["mode"] == "local-only"
    assert response["external_connections"] is False
    assert {item["provider_id"] for item in response["items"]} >= {
        "unity-catalog-local",
        "polaris-local",
    }


def test_local_catalog_identifier_resolution_is_provider_specific() -> None:
    assert resolve_local_identifier("unity-catalog-local", "main.crm.customers") == {
        "catalog": "main",
        "schema": "crm",
        "table": "customers",
    }
    assert resolve_local_identifier("polaris-local", "lakehouse.crm.customers") == {
        "catalog": "lakehouse",
        "namespace": "crm",
        "table": "customers",
    }
    with pytest.raises(ValueError, match="must follow"):
        resolve_local_identifier("unity-catalog-local", "crm.customers")


def test_plugin_registers_all_application_handlers() -> None:
    plugin = SyntheticDataStudioPlugin()
    contributions = ContributionRegistry()
    for permission in plugin.manifest.permissions:
        contributions.add_permission(permission, plugin.manifest.id)
    plugin.register(PluginContext(plugin.manifest.id, contributions, {}))
    routes = {(item.method, item.path) for item in contributions.routes}
    assert routes == {
        ("GET", "/v1/synthetic-data-studio/formats"),
        ("GET", "/v1/synthetic-data-studio/health"),
        ("GET", "/v1/synthetic-data-studio/runs/{run_id}"),
        ("POST", "/v1/synthetic-data-studio/plans"),
        ("POST", "/v1/synthetic-data-studio/generate"),
        ("POST", "/v1/synthetic-data-studio/generate/async"),
        ("GET", "/v1/synthetic-data-studio/jobs/{job_id}"),
        ("POST", "/v1/synthetic-data-studio/jobs/{job_id}/cancel"),
        ("POST", "/v1/synthetic-data-studio/validate"),
        ("POST", "/v1/synthetic-data-studio/export"),
        ("GET", "/v1/synthetic-data-studio/catalog/providers"),
        ("POST", "/v1/synthetic-data-studio/catalog/resolve"),
        ("GET", "/v1/synthetic-data-studio/catalog/namespaces"),
        ("POST", "/v1/synthetic-data-studio/catalog/namespaces"),
        ("GET", "/v1/synthetic-data-studio/catalog/assets"),
        ("GET", "/v1/synthetic-data-studio/catalog/assets/{asset_id}"),
        ("GET", "/v1/synthetic-data-studio/catalog/assets/{asset_id}/lineage"),
        ("GET", "/v1/synthetic-data-studio/catalog/assets/{asset_id}/revisions"),
        ("GET", "/v1/synthetic-data-studio/runs"),
    }


def test_local_generation_route_executes_deterministic_slice() -> None:
    response = _plugin().generate(body={"plan": _plan()})
    assert response["status"] == "generated"
    assert response["contract"] == "synthetic-data-studio/generation/v1"
    assert response["validation"]["passed"] is True
    assert len(response["tables"][0]["rows"]) == 3


def test_generation_route_reports_privacy_review_for_source_sample() -> None:
    response = _plugin().generate(
        body={
            "plan": _plan(),
            "source_sample": {"customers": [{"customer_id": 1, "email": "user0@example.test"}]},
        }
    )
    assert response["privacy"]["status"] == "review_required"
    assert response["privacy"]["exact_row_matches"] == 1


def test_validation_route_returns_evidence() -> None:
    plugin = _plugin()
    generated = plugin.generate(body={"plan": _plan()})
    response = plugin.validate(body={"plan": _plan(), "run_id": generated["run_id"]})
    assert response["status"] == "validated"
    assert response["evidenceId"].startswith("validation-")


def test_async_generation_job_reaches_terminal_state() -> None:
    plugin = _plugin()
    submitted = plugin.generate_async(body={"plan": _plan()})
    assert submitted["status"] == "queued"
    for _ in range(50):
        status = plugin.get_generation_job(job_id=submitted["job_id"])
        if status["status"] == "completed":
            break
        time.sleep(0.01)
    assert status["status"] == "completed"


def test_json_plan_payload_is_accepted_by_api_surface() -> None:
    response = _plugin().generate(
        body={
            "plan": {
                "seed": 3,
                "tables": [
                    {
                        "name": "events",
                        "rows": 2,
                        "columns": [{"name": "event_id", "kind": "integer", "nullable": False}],
                        "primary_key": "event_id",
                    }
                ],
            }
        }
    )
    assert response["status"] == "generated"
    assert response["tables"][0]["rows"][0]["event_id"] == 1


def test_plugin_enforces_configured_row_limit(monkeypatch) -> None:
    monkeypatch.setenv("SDS_MAX_ROWS_PER_RUN", "1")
    with pytest.raises(ValueError, match="row limit"):
        _plugin().generate(body={"plan": {"tables": [{"name": "events", "rows": 2}]}})


def test_plugin_health_reports_degraded_without_catalog() -> None:
    health = _plugin().health()
    assert health["status"] == "degraded"
    assert health["checks"]["catalog"] == "degraded"


def test_export_route_serializes_a_generated_table() -> None:
    plugin = _plugin()
    generated = plugin.generate(body={"plan": _plan()})
    response = plugin.export(
        body={"run_id": generated["run_id"], "format_id": "jsonl", "table": "customers"}
    )
    assert response["status"] == "completed"
    assert response["content"].count("\n") == 3


def test_export_route_can_materialize_a_content_addressed_artifact(tmp_path) -> None:
    plugin = _plugin(artifact_store=LocalArtifactStore(tmp_path / "artifacts"))
    generated = plugin.generate(body={"plan": _plan()})
    response = plugin.export(
        body={"run_id": generated["run_id"], "format_id": "csv", "table": "customers"}
    )
    assert response["artifact"]["storage_ref"].startswith("artifact://sha256/")


def test_export_route_fails_closed_for_unknown_format() -> None:
    plugin = _plugin()
    generated = plugin.generate(body={"plan": _plan()})
    with pytest.raises(ValueError, match="unknown exporter"):
        plugin.export(
            body={"run_id": generated["run_id"], "format_id": "parquet", "table": "customers"}
        )


def test_register_uses_host_injected_service_and_artifact_store(tmp_path) -> None:
    service = GovernStudioService(SqliteRunStore(str(tmp_path / "runs.db")))
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    plugin = SyntheticDataStudioPlugin()
    contributions = ContributionRegistry()
    for permission in plugin.manifest.permissions:
        contributions.add_permission(permission, plugin.manifest.id)
    plugin.register(
        PluginContext(
            plugin.manifest.id,
            contributions,
            {"govern_studio_service": service, "artifact_store": artifacts},
        )
    )
    assert plugin.service is service
    assert plugin.artifact_store is artifacts


def test_plugin_host_invokes_generate_validate_and_export_routes() -> None:
    plugin = SyntheticDataStudioPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)
    manager.start(plan)
    try:
        generated = host.invoke_route(
            "POST", "/v1/synthetic-data-studio/generate", body={"plan": _plan()}
        )
        run_id = generated["run_id"]
        validated = host.invoke_route(
            "POST",
            "/v1/synthetic-data-studio/validate",
            body={"plan": _plan(), "run_id": run_id},
        )
        exported = host.invoke_route(
            "POST",
            "/v1/synthetic-data-studio/export",
            body={"run_id": run_id, "format_id": "json", "table": "customers"},
        )
        assert validated["status"] == "validated"
        assert exported["status"] == "completed"
    finally:
        manager.stop(plan)


def test_plugin_can_use_durable_service_across_restart(tmp_path) -> None:
    database = tmp_path / "synthetic.db"
    first = _plugin(GovernStudioService(SqliteRunStore(str(database))))
    created = first.generate(body={"plan": _plan()}, idempotency_key="durable-1")
    second = _plugin(GovernStudioService(SqliteRunStore(str(database))))
    restored = second.service.get_run(created["run_id"])
    assert restored.run_id == created["run_id"]
    assert restored.result is not None


def test_plugin_run_query_is_available_through_composed_runtime() -> None:
    plugin = _plugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)
    plugin.generate(body={"plan": _plan()}, idempotency_key="runtime-run")
    run = plugin.service.snapshot()[0]
    response = host.invoke_route("GET", f"/v1/synthetic-data-studio/runs/{run.run_id}")
    assert response["run_id"] == run.run_id
    assert response["hasResult"] is True


def test_plugin_catalog_routes_read_assets_and_lineage(tmp_path) -> None:
    now = Instant("2026-01-01T00:00:00.000000Z")
    database = tmp_path / "catalog.db"
    workspace_id = WorkspaceId("workspace-a")
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace_id, "Workspace A"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    source = CatalogAsset(AssetId("crm.customers"), "dataset", "customers")
    source_ref = AssetRef(source.id, AssetVersion("1"))
    catalog.create_asset(workspace_id, source, now=now)
    catalog.put_revision(workspace_id, AssetRevision(source_ref), now=now)
    plugin = _plugin()
    contributions = ContributionRegistry()
    for permission in plugin.manifest.permissions:
        contributions.add_permission(permission, plugin.manifest.id)
    plugin.register(PluginContext(plugin.manifest.id, contributions, {"catalog_store": catalog}))
    assets = plugin.list_assets(body={"workspace_id": "workspace-a"})
    assert assets["items"][0]["id"] == "crm.customers"
    filtered = plugin.list_assets(query="workspace_id=workspace-a&search=customers")
    assert filtered["search"] == "customers"
    assert [item["id"] for item in filtered["items"]] == ["crm.customers"]
    detail = plugin.get_asset(asset_id="crm.customers", body={"workspace_id": "workspace-a"})
    assert detail["asset"]["name"] == "customers"
    revisions = plugin.list_revisions(
        asset_id="crm.customers", body={"workspace_id": "workspace-a"}
    )
    assert revisions["items"][0]["ref"]["version"] == "1"
    lineage = plugin.get_lineage(
        asset_id="crm.customers", body={"workspace_id": "workspace-a", "version": "1"}
    )
    assert lineage["upstream"] == []


def test_catalog_namespaces_are_persisted(tmp_path) -> None:
    now = Instant("2026-01-01T00:00:00.000000Z")
    database = tmp_path / "catalog.db"
    workspace_id = WorkspaceId("workspace-a")
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace_id, "A"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    registered = catalog.register_namespace(
        workspace_id,
        provider_id="polaris-local",
        identifier="lake.crm",
        namespace={"catalog": "lake", "namespace": "crm"},
        now=now,
    )
    assert registered["identifier"] == "lake.crm"
    assert catalog.list_namespaces(workspace_id)[0]["provider_id"] == "polaris-local"


def test_catalog_identifier_resolution_route() -> None:
    response = _plugin().resolve_catalog_identifier(
        body={
            "provider_id": "polaris-local",
            "identifier": "lakehouse.crm.customers",
        }
    )
    assert response["namespace"] == {
        "catalog": "lakehouse",
        "namespace": "crm",
        "table": "customers",
    }
