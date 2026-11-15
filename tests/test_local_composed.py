from __future__ import annotations

import asyncio
import csv
import http.client
import json
import socket
import time
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pyronin import APIError, HTTPTransport, Ronin
from studio_cli import main as cli_main
from studio_cli.local_composed import (
    _catalog_reader_for_backend,
    _workflow_reader_for_backend,
    build_local_composed_from_env,
)
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    ConnectionDefinition,
    ConnectionId,
    DataContract,
    ExecutionProfile,
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    LineageEdge,
    ObjectType,
    OntologyDefinition,
    OntologyId,
    OwnershipMetadata,
    Pipeline,
    Project,
    ProjectId,
    ProjectManifest,
    PropertyDefinition,
    QualityRule,
    QualityRuleId,
    RepositoryBinding,
    RuntimeProfileRef,
    Schedule,
    ScheduleId,
    SensitivityMetadata,
    WorkflowDefinition,
    WorkflowId,
    Workspace,
    WorkspaceId,
)
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.scheduler_events import EventTriggerDefinition, EventTriggerId
from studio_execution import PostgresWorkflowHTTPAdapter, SqliteWorkflowHTTPAdapter
from studio_lakehouse import write_parquet_rows
from studio_ml import FeatureSpec, Lab
from studio_ml.domain import PipelineIR
from studio_ml.orchestration import JobStoreExecutionStore
from studio_notebook import (
    CellIdentityAnchor,
    Notebook,
    NotebookCell,
    NotebookDocument,
    allocate_cell_ids,
)
from studio_observability import AlertRule, SqliteTelemetryStore
from studio_orchestrator import Instant
from studio_server import LocalServerComposition
from studio_sql import SqlExplainUnsupportedError, SqlTimeoutError
from studio_storage import (
    ArtifactRef,
    LocalArtifactStore,
    PostgresSchedulerSnapshotStore,
    SqliteAuditStore,
    SqliteCatalogStore,
    SqliteKnowledgeGraphStore,
)
from studio_storage.local_files import LocalFileConnector
from studio_synthetic_data import ColumnSpec, GenerationPlan, TableSpec
from studio_synthetic_data.application import GovernStudioService, SqliteRunStore

_CONTROL_VALUE = "control-token"


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


def test_local_composed_catalog_journey_persists_and_isolates_workspace_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "workspace.read,workspace.write,workspace.admin,project.read,project.write",
    )
    workspace = WorkspaceId("workspace-1")
    other_workspace = WorkspaceId("workspace-2")
    now = Instant("2026-10-17T00:00:00.000000Z")
    orders = CatalogAsset(
        AssetId("orders"),
        "table",
        "Orders",
        project_id="project-a",
        tags=("sales",),
        classifications=("internal",),
    )
    archive = CatalogAsset(
        AssetId("orders-archive"),
        "table",
        "Orders archive",
        project_id="project-a",
    )
    hidden = CatalogAsset(
        AssetId("orders"),
        "table",
        "Other workspace orders",
        project_id="project-b",
    )
    orders_revision = AssetRevision(
        AssetRef(orders.id, AssetVersion("1")),
        schema_digest="orders-schema-v1",
        metadata=(("owner", "sales"),),
    )
    archive_revision = AssetRevision(
        AssetRef(archive.id, AssetVersion("1")), schema_digest="archive-schema-v1"
    )
    sensitivity = SensitivityMetadata(1, explicit=("internal",))
    ownership = OwnershipMetadata(1, "group/data", ("user/steward",), "sales")

    def request(address, method: str, path: str, body: object | None = None):
        connection = http.client.HTTPConnection(*address, timeout=5)
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

    composition = build_local_composed_from_env()
    catalog = composition.control_plane_server.catalog_reader
    assert catalog is not None
    composition.control_plane_server.workspace_service.create(
        Workspace(other_workspace, "Other workspace"), now=now
    )
    composition.control_plane_server.authorizer.register_workspace(other_workspace)
    catalog.create_asset(other_workspace, hidden, now=now)
    catalog.create_asset(workspace, orders, now=now)
    catalog.create_asset(workspace, archive, now=now)
    catalog.put_revision(workspace, orders_revision, now=now)
    catalog.put_revision(workspace, archive_revision, now=now)
    catalog.put_lineage(
        workspace,
        LineageEdge(orders_revision.ref, archive_revision.ref, "transform", "declared"),
        now=now,
    )
    try:
        composition.start()
        address = composition.control_plane_server.server_address

        status, replaced = request(
            address,
            "PUT",
            "/v1/workspaces/workspace-1/catalog/assets/orders",
            {**orders.to_payload(), "name": "Orders governed"},
        )
        assert status == 200, replaced
        assert replaced["name"] == "Orders governed"
        status, sensitivity_payload = request(
            address,
            "POST",
            "/v1/workspaces/workspace-1/catalog/assets/orders/sensitivity",
            sensitivity.to_payload(),
        )
        assert status == 201, sensitivity_payload
        status, ownership_payload = request(
            address,
            "POST",
            "/v1/workspaces/workspace-1/catalog/assets/orders/ownership",
            ownership.to_payload(),
        )
        assert status == 201, ownership_payload

        status, first_page = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/assets?limit=1&include_governance=true",
        )
        assert status == 200, first_page
        assert first_page["items"] == [
            {
                **replaced,
                "sensitivity": sensitivity.to_payload(),
                "ownership": ownership.to_payload(),
            }
        ]
        cursor = first_page["next_cursor"]
        assert isinstance(cursor, str)
        assert cursor
        status, second_page = request(
            address,
            "GET",
            f"/v1/workspaces/workspace-1/catalog/assets?limit=1&cursor={cursor}",
        )
        assert status == 200, second_page
        assert second_page == {"items": [archive.to_payload()], "next_cursor": None}

        status, search_page = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/assets?q=sales",
        )
        assert status == 200, search_page
        assert [item["id"] for item in search_page["items"]] == ["orders"]

        status, revisions = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/assets/orders/revisions",
        )
        assert status == 200, revisions
        assert revisions == {"items": [orders_revision.to_payload()]}
        status, revision_payload = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/assets/orders/revisions/1",
        )
        assert status == 200, revision_payload
        assert revision_payload == orders_revision.to_payload()

        status, lineage = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/lineage/orders-archive/1?direction=upstream",
        )
        assert status == 200, lineage
        assert lineage["items"] == [
            LineageEdge(
                orders_revision.ref, archive_revision.ref, "transform", "declared"
            ).to_payload()
        ]

        status, isolated_page = request(address, "GET", "/v1/workspaces/workspace-2/catalog/assets")
        assert status == 200, isolated_page
        assert isolated_page["items"] == [hidden.to_payload()]
    finally:
        composition.stop()

    restarted = build_local_composed_from_env()
    try:
        restarted.start()
        address = restarted.control_plane_server.server_address
        status, persisted = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/assets?include_governance=true",
        )
        assert status == 200, persisted
        assert persisted["items"][0]["name"] == "Orders governed"
        assert persisted["items"][0]["sensitivity"] == sensitivity.to_payload()
        assert persisted["items"][0]["ownership"] == ownership.to_payload()
    finally:
        restarted.stop()

    monkeypatch.setenv("RONIN_CONTROL_PLANE_PERMISSIONS", "workspace.read")
    readonly = build_local_composed_from_env()
    try:
        readonly.start()
        address = readonly.control_plane_server.server_address
        status, _ = request(address, "GET", "/v1/workspaces/workspace-1/catalog/assets")
        assert status == 200
        status, denied = request(
            address,
            "POST",
            "/v1/workspaces/workspace-1/catalog/assets",
            CatalogAsset(AssetId("denied"), "table", "Denied").to_payload(),
        )
        assert status == 403
        assert denied["error"]["code"] == "forbidden"
    finally:
        readonly.stop()


def test_local_composed_graph_and_ontology_journey_isolates_workspaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "workspace.read,workspace.write,workspace.admin,project.read,project.write",
    )
    workspace = WorkspaceId("workspace-1")
    other_workspace = WorkspaceId("workspace-2")
    now = Instant("2026-10-17T00:00:00.000000Z")
    customers = CatalogAsset(AssetId("customers"), "table", "Customers", project_id="project-a")
    customer_revision = AssetRevision(
        AssetRef(customers.id, AssetVersion("1")), schema_digest="customers-schema-v1"
    )
    person_type = ObjectType(
        "Person",
        AssetRef(customers.id, AssetVersion("1")),
        ("id",),
        (
            PropertyDefinition("id", "string", "id", required=True),
            PropertyDefinition("name", "string", "name", required=True),
        ),
    )
    ontology = OntologyDefinition(OntologyId("sales"), "v1", "Sales", (person_type,))
    ada = KnowledgeObject(KnowledgeObjectRef("Person", (("id", "1"),)), (("name", "Ada"),))
    ada_order = KnowledgeObject(KnowledgeObjectRef("Order", (("id", "10"),)), (("total", 10),))
    grace = KnowledgeObject(KnowledgeObjectRef("Person", (("id", "2"),)), (("name", "Grace"),))

    def request(address, method: str, path: str, body: object | None = None):
        connection = http.client.HTTPConnection(*address, timeout=5)
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

    composition = build_local_composed_from_env()
    catalog = composition.control_plane_server.catalog_reader
    ontology_reader = composition.control_plane_server.ontology_reader
    assert catalog is not None
    assert ontology_reader is not None
    composition.control_plane_server.workspace_service.create(
        Workspace(other_workspace, "Other workspace"), now=now
    )
    composition.control_plane_server.authorizer.register_workspace(other_workspace)
    catalog.create_asset(workspace, customers, now=now)
    catalog.put_revision(workspace, customer_revision, now=now)
    cast(Any, ontology_reader).put_schema(workspace, ontology, now=now)
    graph_store = SqliteKnowledgeGraphStore(tmp_path / "ronin.sqlite3")
    graph_store.put(
        workspace, "sales", KnowledgeGraph((ada, ada_order), ((ada.ref, ada_order.ref),))
    )
    graph_store.put(other_workspace, "sales", KnowledgeGraph((grace,), ()))

    try:
        composition.start()
        address = composition.control_plane_server.server_address
        base_url = f"http://{address[0]}:{address[1]}"
        sdk = Ronin(
            transport=HTTPTransport(
                base_url,
                token=_CONTROL_VALUE,
                allow_insecure_localhost=True,
                max_retries=0,
            )
        )
        monkeypatch.setenv("RONIN_CONTROL_PLANE_URL", base_url)
        monkeypatch.setenv("RONIN_TOKEN", _CONTROL_VALUE)

        sdk_assets = sdk.list_catalog_assets("workspace-1")
        assert sdk_assets
        assert sdk_assets[0].id == "customers"
        sdk_revisions = sdk.list_catalog_revisions("workspace-1", "customers")
        assert sdk_revisions[0]["ref"]["version"] == "1"
        assert (
            sdk.get_catalog_revision("workspace-1", "customers", "1")["ref"]["asset_id"]
            == "customers"
        )
        assert sdk.list_catalog_lineage("workspace-1", "customers", "1") == ()
        assert sdk.list_ontology_versions("workspace-1", "sales")[0]["version"] == "v1"
        assert sdk.get_ontology_schema("workspace-1", "sales", "v1")["id"] == "sales"

        assert cli_main(["catalog", "assets", "workspace-1", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["items"][0]["id"] == "customers"
        assert cli_main(["catalog", "revision", "workspace-1", "customers", "1", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["ref"]["asset_id"] == "customers"
        assert cli_main(["ontology", "schema", "workspace-1", "sales", "v1", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["id"] == "sales"

        status, versions = request(address, "GET", "/v1/workspaces/workspace-1/ontologies/sales")
        assert status == 200, versions
        assert versions == {"items": [ontology.to_payload()]}
        status, version = request(address, "GET", "/v1/workspaces/workspace-1/ontologies/sales/v1")
        assert status == 200, version
        assert version == ontology.to_payload()

        status, query = request(
            address,
            "POST",
            "/v1/workspaces/workspace-1/graphs/sales/query",
            {"query": "SELECT Person WHERE name = 'Ada' LIMIT 10"},
        )
        assert status == 200, query
        assert query["objects"] == [
            {
                "object_type": "Person",
                "key": [["id", "1"]],
                "properties": [["name", "Ada"]],
            }
        ]
        assert sdk.query_graph("workspace-1", "sales", "SELECT Person WHERE name = 'Ada' LIMIT 10")[
            "objects"
        ][0]["properties"] == [["name", "Ada"]]
        assert (
            cli_main(
                [
                    "graphs",
                    "query",
                    "workspace-1",
                    "sales",
                    "SELECT Person WHERE name = 'Ada' LIMIT 10",
                    "--json",
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["objects"][0]["key"] == [["id", "1"]]
        status, objects = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/graphs/sales/objects/Person?limit=10",
        )
        assert status == 200, objects
        assert objects["items"][0]["key"] == [["id", "1"]]
        assert sdk.list_graph_objects("workspace-1", "sales", "Person")[0]["key"] == [["id", "1"]]
        assert cli_main(["graphs", "objects", "workspace-1", "sales", "Person", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["items"][0]["object_type"] == "Person"
        status, neighbors = request(
            address,
            "POST",
            "/v1/workspaces/workspace-1/graphs/sales/neighbors",
            {"object_type": "Person", "key": [["id", "1"]], "limit": 10},
        )
        assert status == 200, neighbors
        assert neighbors["items"] == [{"object_type": "Order", "key": [["id", "10"]]}]
        assert sdk.graph_neighbors("workspace-1", "sales", "Person", [["id", "1"]])[0] == {
            "object_type": "Order",
            "key": [["id", "10"]],
        }
        assert (
            cli_main(
                [
                    "graphs",
                    "neighbors",
                    "workspace-1",
                    "sales",
                    "Person",
                    '[["id","1"]]',
                    "--json",
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["items"][0]["object_type"] == "Order"
        assert cli_main(["graphs", "neighbors", "workspace-1", "sales", "Person", "not-json"]) == 2
        assert "graph key must be valid JSON" in capsys.readouterr().err
        with pytest.raises(APIError) as sdk_denied:
            sdk.query_graph("workspace-unknown", "sales", "SELECT Person LIMIT 1")
        assert sdk_denied.value.status_code == 403

        status, isolated_query = request(
            address,
            "POST",
            "/v1/workspaces/workspace-2/graphs/sales/query",
            {"query": "SELECT Person WHERE name = 'Grace' LIMIT 10"},
        )
        assert status == 200, isolated_query
        assert isolated_query["objects"][0]["properties"] == [["name", "Grace"]]
        status, no_leak = request(
            address,
            "POST",
            "/v1/workspaces/workspace-2/graphs/sales/query",
            {"query": "SELECT Person WHERE name = 'Ada' LIMIT 10"},
        )
        assert status == 200, no_leak
        assert no_leak == {"objects": []}
        status, denied = request(
            address,
            "POST",
            "/v1/workspaces/workspace-unknown/graphs/sales/query",
            {"query": "SELECT Person LIMIT 10"},
        )
        assert status == 403, denied
        assert denied["error"]["code"] == "forbidden"
    finally:
        composition.stop()

    restarted = build_local_composed_from_env()
    try:
        restarted.start()
        assert sdk.query_graph("workspace-1", "sales", "SELECT Person WHERE name = 'Ada' LIMIT 10")[
            "objects"
        ][0]["properties"] == [["name", "Ada"]]
        status, persisted = request(
            restarted.control_plane_server.server_address,
            "POST",
            "/v1/workspaces/workspace-1/graphs/sales/query",
            {"query": "SELECT Person WHERE name = 'Ada' LIMIT 10"},
        )
        assert status == 200, persisted
        assert persisted["objects"][0]["properties"] == [["name", "Ada"]]
    finally:
        restarted.stop()


def test_local_composed_quality_contract_journey_is_durable_and_operator_visible(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "workspace.read,workspace.write,workspace.admin,project.read,project.write",
    )
    workspace = WorkspaceId("workspace-1")
    now = Instant("2026-10-17T00:00:00.000000Z")
    asset = CatalogAsset(AssetId("orders"), "table", "Orders", project_id="project-a")
    revision = AssetRevision(AssetRef(asset.id, AssetVersion("1")), schema_digest="orders-v1")
    contract = DataContract(
        revision.ref,
        "exact",
        (
            QualityRule(
                QualityRuleId("non-empty"),
                "row_count",
                "At least one order",
                blocking=True,
                parameters=(("min", "1"),),
            ),
        ),
    )
    composition = build_local_composed_from_env()
    catalog = composition.control_plane_server.catalog_reader
    assert catalog is not None
    catalog.create_asset(workspace, asset, now=now)
    catalog.put_revision(workspace, revision, now=now)
    derived_asset = CatalogAsset(
        AssetId("orders-derived"), "table", "Derived orders", project_id="project-a"
    )
    derived_revision = AssetRevision(
        AssetRef(derived_asset.id, AssetVersion("1")), schema_digest="orders-derived-v1"
    )
    catalog.create_asset(workspace, derived_asset, now=now)
    catalog.put_revision(workspace, derived_revision, now=now)
    catalog.put_lineage(
        workspace,
        LineageEdge(revision.ref, derived_revision.ref, "transform", "declared"),
        now=now,
    )
    assert composition.control_plane_server.alert_reader is not None
    telemetry = SqliteTelemetryStore(tmp_path / "ronin.sqlite3")
    alert_rule = AlertRule(
        "quality-run-failed",
        "Quality run failures",
        "quality.run.failure",
        "gte",
        1.0,
        (("asset", "orders@1"),),
    )
    telemetry.put_alert_rule(alert_rule)

    def request(
        address: tuple[str, int], method: str, path: str, body: object | None = None
    ) -> tuple[int, dict[str, object]]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Authorization": "Bearer control-token"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(*address, timeout=5)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, cast(
                dict[str, object], json.loads(response.read().decode("utf-8"))
            )
        finally:
            connection.close()

    composition.start()
    address = composition.control_plane_server.server_address
    base_url = f"http://{address[0]}:{address[1]}"
    sdk = Ronin(
        transport=HTTPTransport(
            base_url,
            token=_CONTROL_VALUE,
            allow_insecure_localhost=True,
            max_retries=0,
        )
    )
    monkeypatch.setenv("RONIN_CONTROL_PLANE_URL", base_url)
    monkeypatch.setenv("RONIN_TOKEN", _CONTROL_VALUE)
    contract_file = tmp_path / "quality-contract.json"
    contract_file.write_text(json.dumps(contract.to_payload()), encoding="utf-8")
    passed_file = tmp_path / "quality-run-passed.json"
    passed_file.write_text(
        json.dumps(
            {
                "asset": {"asset_id": "orders", "version": "1"},
                "rows": [{"id": 1}],
                "run_id": "quality-local-passed",
                "execution_ref": "quality-execution-passed",
                "contract_digest": contract.digest,
                "enforce_blocking": True,
            }
        ),
        encoding="utf-8",
    )
    try:
        assert (
            sdk.put_quality_contract("workspace-1", "orders", "1", contract.to_payload())
            == contract.to_payload()
        )
        assert sdk.get_quality_contract("workspace-1", "orders", "1") == contract.to_payload()
        passed = sdk.run_quality(
            "workspace-1",
            {
                "asset": {"asset_id": "orders", "version": "1"},
                "rows": [{"id": 1}],
                "run_id": "quality-local-passed",
                "execution_ref": "quality-execution-passed",
                "contract_digest": contract.digest,
                "enforce_blocking": True,
            },
        )
        assert passed["gate_passed"] is True
        passed_run = cast(dict[str, object], passed["run"])
        assert passed_run["status"] == "passed"
        assert passed_run["execution_ref"] == "quality-execution-passed"
        assert sdk.list_quality_runs("workspace-1", "orders", "1")[0]["id"] == (
            "quality-local-passed"
        )
        assert sdk.get_quality_state("workspace-1", "orders", "1")["latest_status"] == ("passed")
        status, alert_payload = request(
            address, "GET", "/v1/workspaces/workspace-1/alerts/instances"
        )
        assert status == 200, alert_payload
        assert cast(list[object], alert_payload["items"]) == []

        assert cli_main(["quality", "contract", "get", "workspace-1", "orders", "1", "--json"]) == 0
        assert json.loads(capsys.readouterr().out) == contract.to_payload()
        assert (
            cli_main(
                [
                    "quality",
                    "contract",
                    "put",
                    "workspace-1",
                    "orders",
                    "1",
                    str(contract_file),
                    "--json",
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out) == contract.to_payload()
        assert cli_main(["quality", "run", "workspace-1", str(passed_file), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["gate_passed"] is True

        failed_request = {
            "asset": {"asset_id": "orders", "version": "1"},
            "rows": [],
            "run_id": "quality-local-failed",
            "execution_ref": "quality-execution-failed",
            "contract_digest": contract.digest,
            "enforce_blocking": False,
        }
        failed = sdk.run_quality("workspace-1", failed_request)
        assert failed["gate_passed"] is False
        assert cast(dict[str, object], failed["run"])["status"] == "failed"
        assert sdk.get_quality_state("workspace-1", "orders", "1")["latest_status"] == ("failed")
        status, alert_payload = request(
            address, "GET", "/v1/workspaces/workspace-1/alerts/instances"
        )
        assert status == 200, alert_payload
        alert_items = cast(list[dict[str, object]], alert_payload["items"])
        assert len(alert_items) == 1
        assert alert_items[0]["rule_id"] == alert_rule.id
        fingerprint = cast(str, alert_items[0]["fingerprint"])
        assert cli_main(["alerts", "rules", "workspace-1", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["items"] == [alert_rule.to_payload()]
        assert cli_main(["alerts", "instances", "workspace-1", "--json"]) == 0
        cli_instances = json.loads(capsys.readouterr().out)
        assert cli_instances["items"][0]["fingerprint"] == fingerprint
        status, evaluated = request(
            address,
            "POST",
            "/v1/workspaces/workspace-1/alerts/evaluate",
            {"rule_id": alert_rule.id},
        )
        assert status == 200, evaluated
        assert evaluated["changed"] is False
        assert cast(dict[str, object], evaluated["state"])["status"] == "open"
        status, catalog_quality = request(
            address, "GET", "/v1/workspaces/workspace-1/catalog/assets?include_quality=true"
        )
        assert status == 200, catalog_quality
        catalog_items = cast(list[dict[str, object]], catalog_quality["items"])
        orders_catalog = next(item for item in catalog_items if item["id"] == "orders")
        orders_quality = cast(dict[str, object], orders_catalog["quality"])
        orders_state = cast(dict[str, object], orders_quality["state"])
        assert orders_state["latest_status"] == "failed"
        assert orders_state["latest_run_id"] == "quality-local-failed"
        assert cli_main(["catalog", "assets", "workspace-1", "--include-quality", "--json"]) == 0
        cli_catalog_items = cast(dict[str, object], json.loads(capsys.readouterr().out))["items"]
        cli_orders = next(
            item
            for item in cast(list[dict[str, object]], cli_catalog_items)
            if item["id"] == "orders"
        )
        assert cast(dict[str, object], cast(dict[str, object], cli_orders)["quality"])["state"]
        status, lineage_quality = request(
            address,
            "GET",
            "/v1/workspaces/workspace-1/catalog/lineage/orders-derived/1"
            "?direction=upstream&include_quality=true",
        )
        assert status == 200, lineage_quality
        lineage_item = cast(list[dict[str, object]], lineage_quality["items"])[0]
        assert cast(dict[str, object], lineage_item["source_quality"])["latest_status"] == "failed"
        assert cast(dict[str, object], lineage_item["target_quality"])["latest_status"] == "unknown"
        assert cli_main(["alerts", "evaluate", "workspace-1", alert_rule.id, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["changed"] is False
        assert (
            cli_main(
                [
                    "alerts",
                    "acknowledge",
                    "workspace-1",
                    alert_rule.id,
                    fingerprint,
                    "--json",
                ]
            )
            == 0
        )
        acknowledged = json.loads(capsys.readouterr().out)
        assert acknowledged["state"]["acknowledged_at"] is not None
        assert sdk.run_quality("workspace-1", failed_request) == failed
        assert len(telemetry.list_metrics()) == 4
        with pytest.raises(APIError) as malformed:
            sdk.run_quality(
                "workspace-1",
                {
                    "asset": {"asset_id": "orders", "version": "1"},
                    "rows": [["not", "an", "object"]],
                    "run_id": "quality-local-malformed",
                    "contract_digest": contract.digest,
                    "enforce_blocking": False,
                },
            )
        assert malformed.value.status_code == 400

        assert cli_main(["quality", "history", "workspace-1", "orders", "1", "--json"]) == 0
        history = json.loads(capsys.readouterr().out)
        assert [item["id"] for item in history["items"]] == [
            "quality-local-passed",
            "quality-local-failed",
        ]
        assert cli_main(["quality", "state", "workspace-1", "orders", "1", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["latest_run_id"] == "quality-local-failed"
        with pytest.raises(APIError) as denied:
            sdk.get_quality_state("workspace-unknown", "orders", "1")
        assert denied.value.status_code == 403
    finally:
        composition.stop()

    restarted = build_local_composed_from_env()
    try:
        restarted.start()
        assert sdk.get_quality_contract("workspace-1", "orders", "1") == contract.to_payload()
        recovered = sdk.get_quality_state("workspace-1", "orders", "1")
        assert recovered["latest_run_id"] == "quality-local-failed"
        assert [item["status"] for item in cast(list[dict[str, object]], recovered["history"])] == [
            "passed",
            "failed",
        ]
        status, recovered_alerts = request(
            restarted.control_plane_server.server_address,
            "GET",
            "/v1/workspaces/workspace-1/alerts/instances",
        )
        assert status == 200, recovered_alerts
        recovered_items = cast(list[dict[str, object]], recovered_alerts["items"])
        assert recovered_items[0]["status"] == "open"
        assert recovered_items[0]["acknowledged_at"] is not None
    finally:
        restarted.stop()


def test_local_composed_persists_notebook_revisions_across_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "workspace.read,workspace.write,project.read,project.write",
    )
    project_id = "persistent-notebook-project"
    notebook_id = "persistent-notebook"
    anchor = CellIdentityAnchor("authoring", f"{project_id}/notebooks/{notebook_id}", "cell-1")
    cell_id = allocate_cell_ids((anchor,))[0]
    document = NotebookDocument(
        Notebook((NotebookCell(cell_id, "code", "print('persistent')", language="python"),)),
        (anchor,),
    ).to_data()
    manifest = ProjectManifest.from_project(
        Project(
            ProjectId(project_id),
            "Persistent notebook project",
            (RepositoryBinding("code", "https://example.test/notebooks.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )
    path = f"/v1/workspaces/workspace-1/projects/{project_id}/notebooks/{notebook_id}"
    collection_path = f"/v1/workspaces/workspace-1/projects/{project_id}/notebooks"

    def request(address, method: str, request_path: str, body: object | None = None):
        connection = http.client.HTTPConnection(*address, timeout=5)
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": "Bearer control-token"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, request_path, body=encoded, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    composition = build_local_composed_from_env()
    try:
        composition.control_plane_server.project_service.register(
            WorkspaceId("workspace-1"), manifest, now=Instant("2026-10-17T00:00:00.000000Z")
        )
        composition.start()
        status, created = request(
            composition.control_plane_server.server_address,
            "POST",
            collection_path,
            {"id": notebook_id, "document": document},
        )
        assert status == 201, created
        assert created["revision"] == 1
    finally:
        composition.stop()

    restarted = build_local_composed_from_env()
    try:
        restarted.start()
        status, loaded = request(restarted.control_plane_server.server_address, "GET", path)
        assert status == 200, loaded
        assert loaded["revision"] == 1
        assert loaded["document"] == document
    finally:
        restarted.stop()


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


def test_local_composed_scheduler_api_and_daemon_journey(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Exercise the real local HTTP adapter, durable store and daemon together."""

    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    composition = build_local_composed_from_env()
    workspace_id = WorkspaceId("workspace-1")
    now = Instant("2026-09-17T00:00:00.000000Z")
    workflow = WorkflowDefinition(WorkflowId("workflow-1"), "Local scheduler workflow", Pipeline())
    workflow_reader = composition.control_plane_server.workflow_reader
    assert workflow_reader is not None
    store = workflow_reader._store  # type: ignore[attr-defined]
    store.put_workflow(workspace_id, workflow, now=now)
    schedule = Schedule(ScheduleId("daily"), workflow.id, "0 * * * *", "UTC", True)
    schedule_path = "/v1/workspaces/workspace-1/schedules/daily"
    run_path = "/v1/workspaces/workspace-1/workflows/workflow-1/runs"

    def request(method: str, path: str, body: object | None = None) -> tuple[int, object]:
        connection = http.client.HTTPConnection(
            *composition.control_plane_server.server_address, timeout=5
        )
        payload = None if body is None else json.dumps(body, separators=(",", ":"))
        headers = {"Authorization": "Bearer control-token"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    def wait_for(path: str, predicate, *, timeout: float = 12.0) -> object:
        deadline = time.monotonic() + timeout
        last: object = None
        while time.monotonic() < deadline:
            status, last = request("GET", path)
            if status == 200 and predicate(last):
                return last
            time.sleep(0.1)
        raise AssertionError(f"timed out waiting for {path}: {last!r}")

    try:
        composition.start()
        assert composition.ready

        status, payload = request(
            "PUT",
            schedule_path,
            schedule.to_payload(),
        )
        assert status == 200, payload
        status, payload = request("GET", schedule_path)
        assert status == 200, payload
        assert payload["id"] == "daily"  # type: ignore[index]

        status, payload = request("GET", f"{schedule_path}/next-runs?after={now}&count=2")
        assert status == 200, payload
        assert len(payload["items"]) == 2  # type: ignore[index]

        status, payload = request(
            "POST",
            run_path,
            {
                "trigger": {"kind": "api", "key": "studio-run-1", "source_ref": "studio"},
                "idempotency_key": "studio-run-1",
            },
        )
        assert status == 201, payload
        run_id = payload["id"]  # type: ignore[index]
        status, payload = request(
            "POST",
            f"/v1/workspaces/workspace-1/workflow-runs/{run_id}/cancel",
        )
        assert status == 200, payload

        trigger = EventTriggerDefinition(
            EventTriggerId("on-data"), workflow.id, "dataset.ready", source_ref="studio"
        )
        status, payload = request(
            "PUT",
            "/v1/workspaces/workspace-1/event-triggers/on-data",
            trigger.to_payload(),
        )
        assert status == 200, payload

        invalid_event = {
            "event_id": "event-invalid",
            "event_type": "dataset.ready",
            "payload_digest": "a" * 64,
            "occurred_at": str(now),
            "source_ref": 42,
        }
        status, payload = request("POST", "/v1/workspaces/workspace-1/events", invalid_event)
        assert status == 400, payload
        assert payload["error"]["code"] == "invalid_request"  # type: ignore[index]

        invalid_backfill = {
            "id": 42,
            "schedule_id": "daily",
            "start_at": "2026-09-16T00:00:00.000000Z",
            "end_at": "2026-09-16T02:00:00.000000Z",
        }
        status, payload = request("POST", "/v1/workspaces/workspace-1/backfills", invalid_backfill)
        assert status == 400, payload
        assert payload["error"]["code"] == "invalid_request"  # type: ignore[index]

        status, payload = request(
            "POST",
            "/v1/workspaces/workspace-1/events",
            {
                "event_id": "event-1",
                "event_type": "dataset.ready",
                "payload_digest": "a" * 64,
                "occurred_at": str(now),
                "source_ref": "studio",
            },
        )
        assert status == 202, payload
        assert payload["deliveries"] == ["pending"]  # type: ignore[index]
        deliveries = wait_for(
            "/v1/workspaces/workspace-1/event-deliveries",
            lambda result: bool(
                isinstance(result, dict)
                and result.get("items")
                and result["items"][0]["state"] == "delivered"
            ),
        )
        assert deliveries["items"][0]["workflow_run_id"].startswith(  # type: ignore[index]
            "workflow-run-event-"
        )

        status, payload = request(
            "POST",
            "/v1/workspaces/workspace-1/backfills/preview",
            {
                "schedule_id": "daily",
                "start_at": "2026-09-16T00:00:00.000000Z",
                "end_at": "2026-09-16T02:00:00.000000Z",
                "max_runs": 3,
            },
        )
        assert status == 200, payload
        assert len(payload["items"]) == 3  # type: ignore[index]

        status, payload = request(
            "POST",
            "/v1/workspaces/workspace-1/backfills",
            {
                "id": "backfill-1",
                "schedule_id": "daily",
                "start_at": "2026-09-16T00:00:00.000000Z",
                "end_at": "2026-09-16T02:00:00.000000Z",
            },
        )
        assert status == 201, payload
        backfill = wait_for(
            "/v1/workspaces/workspace-1/backfills/backfill-1",
            lambda result: (
                isinstance(result, dict) and result.get("state") in {"running", "completed"}
            ),
        )
        assert backfill["state"] == "running"  # type: ignore[index]
        status, payload = request(
            "POST", "/v1/workspaces/workspace-1/backfills/backfill-1/cancel", {}
        )
        assert status == 200, payload
        assert payload["state"] == "cancelled"  # type: ignore[index]
    finally:
        composition.stop()


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


def test_local_composed_ml_train_register_predict_and_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Exercise the real local ML HTTP/SQLite/artifact path end to end."""

    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_unused_port()))
    monkeypatch.setenv("RONIN_PORT", str(_unused_port()))
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "workspace.read,workspace.write,workspace.admin,project.read,project.write,scheduler.write",
    )
    now = Instant("2026-10-17T00:00:00.000000Z")
    dataset = CatalogAsset(AssetId("customers"), "table", "Customers", project_id="project-1")
    dataset_revision = AssetRevision(
        AssetRef(dataset.id, AssetVersion("1")), schema_digest="customers-schema-v1"
    )
    rows = [{"x": value, "target": value % 2} for value in range(1, 21)]
    lab_payload = {
        "schema": "ronin.ml-lab/v1",
        "id": "local-ml-lab",
        "name": "Local ML lab",
        "project_id": "project-1",
        "dataset": {"asset_id": "customers", "version": "1"},
        "target": "target",
        "task": "classification",
        "features": [{"column": "x", "role": "numeric"}],
        "backend_id": "local.sklearn",
        "seed": 7,
        "test_fraction": 0.25,
    }

    def request(
        address: tuple[str, int], method: str, path: str, body: object | None = None
    ) -> tuple[int, dict[str, object]]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Authorization": "Bearer control-token"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(*address, timeout=20)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, cast(
                dict[str, object], json.loads(response.read().decode("utf-8"))
            )
        finally:
            connection.close()

    def wait_for_execution(address: tuple[str, int]) -> dict[str, object]:
        deadline = time.monotonic() + 45
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            status, last = request(
                address,
                "GET",
                "/v1/ml-studio/executions/local-ml-run?workspace_id=workspace-1",
            )
            assert status == 200, last
            if last.get("state") in {"succeeded", "failed"}:
                return last
            time.sleep(0.05)
        raise AssertionError(f"timed out waiting for ML execution: {last!r}")

    composition = build_local_composed_from_env()
    catalog = composition.control_plane_server.catalog_reader
    assert catalog is not None
    catalog.create_asset(WorkspaceId("workspace-1"), dataset, now=now)
    catalog.put_revision(WorkspaceId("workspace-1"), dataset_revision, now=now)
    try:
        composition.start()
        address = composition.control_plane_server.server_address

        status, created = request(
            address, "POST", "/v1/ml-studio/labs?workspace_id=workspace-1", lab_payload
        )
        assert status == 200, created
        lab_digest = Lab.from_payload(created).digest

        status, quality = request(
            address,
            "POST",
            "/v1/ml-studio/labs/local-ml-lab/quality?workspace_id=workspace-1",
            {"rows": rows},
        )
        assert status == 200, quality
        assert quality["passed"] is True

        status, submitted = request(
            address,
            "POST",
            "/v1/ml-studio/labs/local-ml-lab/executions?workspace_id=workspace-1",
            {
                "run_id": "local-ml-run",
                "rows": rows,
                "algorithm": "decision_tree_classifier",
                "preprocessor": "standard_scale",
            },
        )
        assert status == 200, submitted
        assert submitted["run_id"] == "local-ml-run"
        execution = wait_for_execution(address)
        assert execution["state"] == "succeeded", execution
        result = cast(dict[str, object], execution["result"])
        assert result["algorithm"] == "decision_tree_classifier"
        assert result["task"] == "classification"
        assert result["artifact_media_type"] == "application/vnd.ronin.sklearn-tabular+json"
        raw_artifact_digest = result["artifact_digest"]
        assert isinstance(raw_artifact_digest, str)
        assert raw_artifact_digest.startswith("sha256:")
        artifact_digest = raw_artifact_digest.removeprefix("sha256:")
        assert len(artifact_digest) == 64

        status, registered = request(
            address,
            "POST",
            "/v1/ml-studio/executions/local-ml-run/register?workspace_id=workspace-1",
            {"model_id": "local-customers", "version": "v1"},
        )
        assert status == 200, registered
        assert registered["model_id"] == "local-customers"
        assert registered["version"] == "v1"
        assert registered["artifact_digest"] == artifact_digest

        status, card = request(
            address,
            "GET",
            "/v1/ml-studio/models/local-customers/v1/card?workspace_id=workspace-1",
        )
        assert status == 200, card
        card_provenance = cast(dict[str, object], card["provenance"])
        assert card_provenance["artifact_digest"] == artifact_digest
        assert card["dataset"] == [dataset_revision.ref.to_payload()]
        assert card_provenance["source_revision"] == lab_digest

        status, artifact = request(
            address,
            "GET",
            "/v1/ml-studio/models/local-customers/v1/artifact"
            "?workspace_id=workspace-1&offset=0&length=64",
        )
        assert status == 200, artifact
        assert artifact["digest"] == artifact_digest
        assert artifact["offset"] == 0
        artifact_data = artifact["data_base64"]
        assert isinstance(artifact_data, str)
        assert artifact_data

        status, prediction = request(
            address,
            "POST",
            "/v1/ml-studio/models/local-customers/v1/predict?workspace_id=workspace-1",
            {"rows": [{"x": 2.0}, {"x": 19.0}]},
        )
        assert status == 200, prediction
        assert prediction["predictions"] == [0, 1]

        status, denied = request(
            address,
            "GET",
            "/v1/ml-studio/models/local-customers/v1/card?workspace_id=workspace-unknown",
        )
        assert status == 403, denied
    finally:
        composition.stop()

    restarted = build_local_composed_from_env()
    try:
        restarted.start()
        address = restarted.control_plane_server.server_address
        status, recovered_card = request(
            address,
            "GET",
            "/v1/ml-studio/models/local-customers/v1/card?workspace_id=workspace-1",
        )
        assert status == 200, recovered_card
        recovered_provenance = cast(dict[str, object], recovered_card["provenance"])
        assert recovered_provenance["artifact_digest"] == artifact_digest
        status, recovered_prediction = request(
            address,
            "POST",
            "/v1/ml-studio/models/local-customers/v1/predict?workspace_id=workspace-1",
            {"rows": [{"x": 2.0}, {"x": 19.0}]},
        )
        assert status == 200, recovered_prediction
        assert recovered_prediction["predictions"] == [0, 1]
    finally:
        restarted.stop()


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
