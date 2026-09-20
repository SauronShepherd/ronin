from pathlib import Path

from studio_core import AssetId, AssetRef, AssetRevision, AssetVersion, CatalogAsset, Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore
from studio_synthetic_data import (
    ColumnSpec,
    GenerationPlan,
    SyntheticOutputPublisher,
    TableSpec,
    generate,
    make_publication_hook,
)
from studio_synthetic_data.application import GovernStudioService
from studio_synthetic_data.application import SqliteRunStore
from studio_synthetic_data.plugin import SyntheticDataStudioPlugin
from studio_core.plugins import PluginManager, PluginRecord
from studio_runtime import PluginHost


NOW = Instant("2026-01-01T00:00:00.000000Z")


def _catalog(path: Path, workspace: str) -> tuple[SqliteCatalogStore, WorkspaceId]:
    workspace_id = WorkspaceId(workspace)
    SqliteWorkspaceStore(path, migration_now=NOW).create_workspace(
        Workspace(workspace_id, workspace), now=NOW
    )
    return SqliteCatalogStore(path, migration_now=NOW), workspace_id


def test_publish_creates_asset_revision_and_lineage_idempotently(tmp_path: Path) -> None:
    catalog, workspace_id = _catalog(tmp_path / "catalog.db", "workspace-a")
    source_asset = CatalogAsset(AssetId("crm.customers"), "dataset", "customers")
    source_ref = AssetRef(source_asset.id, AssetVersion("1"))
    catalog.create_asset(workspace_id, source_asset, now=NOW)
    catalog.put_revision(workspace_id, AssetRevision(source_ref), now=NOW)
    result = generate(GenerationPlan((TableSpec("customers", (ColumnSpec("id", "integer"),), rows=2),), seed=4))
    publisher = SyntheticOutputPublisher(catalog)

    first = publisher.publish(
        workspace_id=workspace_id,
        source=source_ref,
        output_asset_id="synthetic.customers",
        output_version="run-1",
        result=result,
        run_id="run-1",
        now=NOW,
    )
    second = publisher.publish(
        workspace_id=workspace_id,
        source=source_ref,
        output_asset_id="synthetic.customers",
        output_version="run-1",
        result=result,
        run_id="run-1",
        now=NOW,
    )
    assert first.revision == second.revision
    assert catalog.get_revision(workspace_id, first.revision.ref) == first.revision
    assert catalog.upstream(workspace_id, first.revision.ref) == (first.lineage,)


def test_publish_cannot_cross_workspace(tmp_path: Path) -> None:
    catalog, workspace_a = _catalog(tmp_path / "catalog.db", "workspace-a")
    _, workspace_b = _catalog(tmp_path / "catalog.db", "workspace-b")
    source_asset = CatalogAsset(AssetId("crm.customers"), "dataset", "customers")
    source_ref = AssetRef(source_asset.id, AssetVersion("1"))
    catalog.create_asset(workspace_a, source_asset, now=NOW)
    catalog.put_revision(workspace_a, AssetRevision(source_ref), now=NOW)
    result = generate(GenerationPlan((TableSpec("customers", (ColumnSpec("id", "integer"),), rows=1),)))
    publisher = SyntheticOutputPublisher(catalog)
    try:
        publisher.publish(
            workspace_id=workspace_b,
            source=source_ref,
            output_asset_id="synthetic.customers",
            output_version="run-2",
            result=result,
            run_id="run-2",
            now=NOW,
        )
    except KeyError:
        pass
    else:
        raise AssertionError("cross-workspace source publication must fail")


def test_service_generation_automatically_publishes_catalog_and_lineage(tmp_path: Path) -> None:
    catalog, workspace_id = _catalog(tmp_path / "catalog.db", "workspace-a")
    source_asset = CatalogAsset(AssetId("crm.customers"), "dataset", "customers")
    source_ref = AssetRef(source_asset.id, AssetVersion("1"))
    catalog.create_asset(workspace_id, source_asset, now=NOW)
    catalog.put_revision(workspace_id, AssetRevision(source_ref), now=NOW)
    publisher = SyntheticOutputPublisher(catalog)
    service = GovernStudioService(
        publication_hook=make_publication_hook(
            publisher,
            workspace_id=workspace_id,
            source=source_ref,
            output_asset_id="synthetic.customers",
            now=NOW,
        )
    )
    plan = GenerationPlan((TableSpec("customers", (ColumnSpec("id", "integer"),), rows=2),), seed=9)
    run = service.create_run(plan, idempotency_key="auto-publish")
    generated = service.generate(run.run_id, plan)
    output_ref = AssetRef(AssetId("synthetic.customers"), AssetVersion(run.run_id))
    assert generated.status.value == "generated"
    assert catalog.get_revision(workspace_id, output_ref) is not None
    assert len(catalog.upstream(workspace_id, output_ref)) == 1


def test_composed_runtime_smoke_flow_generates_and_queries_governed_output(tmp_path: Path) -> None:
    now = NOW
    database = tmp_path / "ronin.sqlite3"
    catalog, workspace_id = _catalog(database, "workspace-a")
    source = CatalogAsset(AssetId("crm.customers"), "dataset", "customers")
    source_ref = AssetRef(source.id, AssetVersion("1"))
    catalog.create_asset(workspace_id, source, now=now)
    catalog.put_revision(workspace_id, AssetRevision(source_ref), now=now)
    publisher = SyntheticOutputPublisher(catalog)
    service = GovernStudioService(
        SqliteRunStore(str(database)),
        publication_hook=make_publication_hook(
            publisher,
            workspace_id=workspace_id,
            source=source_ref,
            output_asset_id="synthetic.customers",
            now=now,
        ),
    )
    plugin = SyntheticDataStudioPlugin(service)
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "smoke"),), services={"catalog_store": catalog})
    host = PluginHost(manager, plan)
    payload = {"plan": {"tables": [{"name": "customers", "rows": 2, "columns": [{"name": "id", "kind": "integer"}]}], "seed": 8}}
    generated = host.invoke_route("POST", "/v1/synthetic-data-studio/generate", body=payload, idempotency_key="smoke-1")
    assert generated["status"] == "generated"
    run_id = generated["run_id"]
    output_ref = AssetRef(AssetId("synthetic.customers"), AssetVersion(run_id))
    assert catalog.get_revision(workspace_id, output_ref) is not None
    queried = host.invoke_route("GET", f"/v1/synthetic-data-studio/runs/{run_id}")
    assert queried["hasResult"] is True
    lineage = plugin.get_lineage(asset_id="synthetic.customers", body={"workspace_id": "workspace-a", "version": run_id})
    assert len(lineage["upstream"]) == 1
