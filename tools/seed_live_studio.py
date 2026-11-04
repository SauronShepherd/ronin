"""Seed a tiny, deterministic SQLite graph for the real live Studio journeys."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import quote

from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    LineageEdge,
    Pipeline,
    WorkflowDefinition,
    WorkflowId,
    Workspace,
    WorkspaceId,
)
from studio_lakehouse import write_parquet_rows
from studio_semantic import (
    DashboardDefinition,
    DashboardTile,
    MetricQuery,
    SemanticMeasure,
    SemanticModel,
    SqliteSemanticStore,
    semantic_project_scope,
)
from studio_storage import SqliteCatalogStore, SqliteKnowledgeGraphStore
from studio_storage.scheduler_backfill import SchedulerBackfillStore
from studio_storage.workspaces import SqliteWorkspaceStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-only",
        action="store_true",
        help="seed only the workspace needed by a narrowly filtered live route",
    )
    parser.add_argument(
        "--semantic-only",
        action="store_true",
        help="seed only the workspace and semantic model/dashboard fixture",
    )
    args = parser.parse_args()
    raw_database = os.environ.get("RONIN_DB")
    if not raw_database:
        raise SystemExit("RONIN_DB must identify the isolated live-test SQLite database")
    database = Path(raw_database).expanduser().resolve()
    workspace_id = WorkspaceId(os.environ.get("RONIN_WORKSPACE_ID", "default"))
    now = "2026-09-17T00:00:00.000000Z"
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(workspace_id, "Live Qualification Workspace", "Ephemeral live UI fixture."),
        now=now,
    )
    if args.workspace_only:
        print("Seeded only the isolated workspace required for this filtered live route.")
        return 0

    semantic = SqliteSemanticStore(database)
    semantic_scope = semantic_project_scope(str(workspace_id), "examples/demo")
    configured_parquet_root = os.environ.get("RONIN_SQL_PARQUET_ROOT", "").strip()
    parquet_root = Path(configured_parquet_root or database.parent / "sql-parquet").expanduser()
    project_data = parquet_root / quote(semantic_scope, safe="")
    write_parquet_rows(
        project_data / "live_orders.parquet",
        tuple({"order_id": index + 1} for index in range(5)),
    )
    semantic.put_model(
        semantic_scope,
        SemanticModel(
            "live_sales",
            "Live Sales",
            "live_orders",
            measures=(SemanticMeasure("orders", "count"),),
        ),
    )
    semantic.put_dashboard(
        semantic_scope,
        DashboardDefinition(
            "live_overview",
            "Live Overview",
            (
                DashboardTile(
                    "orders",
                    "Orders",
                    "number",
                    MetricQuery("live_sales", ("orders",)),
                ),
            ),
        ),
    )
    if args.semantic_only:
        print("Seeded only the workspace and semantic assets for the filtered live route.")
        return 0

    person_ref = KnowledgeObjectRef("Person", (("id", "1"),))
    organization_ref = KnowledgeObjectRef("Organization", (("id", "2"),))
    graph = KnowledgeGraph(
        (
            KnowledgeObject(person_ref, (("id", "1"), ("name", "Ronin Live Fixture"))),
            KnowledgeObject(
                organization_ref,
                (("id", "2"), ("name", "Ronin Live Organization")),
            ),
        ),
        ((person_ref, organization_ref),),
    )
    store = SqliteKnowledgeGraphStore(database)
    store.put("graph-1", graph)
    catalog = SqliteCatalogStore(database, migration_now=now)
    source = CatalogAsset(AssetId("live-lineage-source"), "table", "Live source")
    target = CatalogAsset(AssetId("live-lineage-target"), "table", "Live target")
    catalog.create_asset(workspace_id, source, now=now)
    catalog.create_asset(workspace_id, target, now=now)
    source_revision = AssetRevision(
        AssetRef(source.id, AssetVersion("1")), schema_digest="live-source-v1"
    )
    target_revision = AssetRevision(
        AssetRef(target.id, AssetVersion("1")), schema_digest="live-target-v1"
    )
    catalog.put_revision(workspace_id, source_revision, now=now)
    catalog.put_revision(workspace_id, target_revision, now=now)
    catalog.put_lineage(
        workspace_id,
        LineageEdge(source_revision.ref, target_revision.ref, "transform", "observed"),
        now=now,
    )
    # A governed source/destination pair for the real PostgreSQL ingestion UI
    # journey. The source binding deliberately matches the live test's separate
    # ephemeral connection; no credentials are stored in catalog metadata.
    ingestion_source = CatalogAsset(
        AssetId("live-ingestion-source"),
        "table",
        "Live PostgreSQL accounts source",
        project_id="examples/demo",
        properties=(
            ("ronin.connector_id", "postgresql"),
            ("ronin.connection_ref", "pg-live-e2e"),
            ("ronin.asset_ref", "public.ui_page_accounts"),
        ),
    )
    ingestion_target = CatalogAsset(
        AssetId("live-ingestion-target"),
        "table",
        "Live ingested accounts",
        project_id="examples/demo",
    )
    catalog.create_asset(workspace_id, ingestion_source, now=now)
    catalog.put_revision(
        workspace_id,
        AssetRevision(
            AssetRef(ingestion_source.id, AssetVersion("source-v1")),
            schema_digest="live-postgres-accounts-source-v1",
        ),
        now=now,
    )
    catalog.create_asset(workspace_id, ingestion_target, now=now)
    incremental_source = CatalogAsset(
        AssetId("live-ingestion-incremental-source"),
        "table",
        "Live PostgreSQL incremental accounts source",
        project_id="examples/demo",
        properties=(
            ("ronin.connector_id", "postgresql"),
            ("ronin.connection_ref", "pg-live-incremental-e2e"),
            ("ronin.asset_ref", "public.ui_page_accounts"),
        ),
    )
    incremental_target = CatalogAsset(
        AssetId("live-ingestion-incremental-target"),
        "table",
        "Live incrementally ingested accounts",
        project_id="examples/demo",
    )
    catalog.create_asset(workspace_id, incremental_source, now=now)
    catalog.put_revision(
        workspace_id,
        AssetRevision(
            AssetRef(incremental_source.id, AssetVersion("source-v1")),
            schema_digest="live-postgres-incremental-accounts-source-v1",
        ),
        now=now,
    )
    catalog.create_asset(workspace_id, incremental_target, now=now)
    scheduler = SchedulerBackfillStore(database, migration_now=now)
    scheduler.put_workflow(
        workspace_id,
        WorkflowDefinition(WorkflowId("live-main"), "Ronin live scheduler fixture", Pipeline()),
        now=now,
    )
    print(
        "Seeded graph, catalog lineage, and a durable workflow in the isolated live Studio fixture."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
