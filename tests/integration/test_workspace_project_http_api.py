from __future__ import annotations

import asyncio
import http.client
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

from studio_connectors import (
    ArtifactDestinationWriter,
    ConnectorRegistry,
    IngestionSyncService,
    SqliteConnectorCheckpointStore,
)
from studio_connectors.contracts import ConnectorReadResult
from studio_core import (
    AssetHandle,
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    CatalogAssetPage,
    ConnectionId,
    ConnectorCapabilities,
    ConnectorDescriptor,
    ExecutionProfile,
    FieldSchema,
    GlossaryTerm,
    GlossaryTermId,
    OwnershipMetadata,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    SensitivityMetadata,
    SourceCheckpoint,
    Workspace,
    WorkspaceId,
)
from studio_core.plugins import PluginManager, PluginRecord
from studio_execution import DurableExecutionService, ProjectService, WorkspaceService
from studio_orchestrator import AttemptId, Instant, LeaseToken
from studio_plugin_observability import LocalObservabilityBuffer, LoggingPlugin, MonitoringPlugin
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost
from studio_security import Actor, PolicyDecision, Principal, PrincipalId
from studio_server import (
    CONTROL_PLANE_ROUTES,
    ControlPlaneUnavailable,
    WorkspaceProjectHTTPServer,
)
from studio_server.http import DurableHTTPApplication
from studio_storage import LocalArtifactStore, SqliteJobStore
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore
from studio_synthetic_data.plugin import SyntheticDataStudioPlugin
from studio_worker import LocalWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths

_WS_A = WorkspaceId("workspace-a")
_WS_B = WorkspaceId("workspace-b")
_WS_C = WorkspaceId("workspace-c")
_PROJECT = ProjectId("project-1")
_NOW = "2026-09-14T08:45:00.000000Z"


class _Store:
    def __init__(self) -> None:
        self.workspaces: dict[WorkspaceId, Workspace] = {}
        self.projects: dict[tuple[WorkspaceId, ProjectId], ProjectManifest] = {}
        self.calls: dict[str, int] = {}

    def _called(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def create_workspace(self, workspace, *, now):
        del now
        self._called("create_workspace")
        self.workspaces[workspace.id] = workspace
        return workspace

    def get_workspace(self, workspace_id):
        return self.workspaces.get(workspace_id)

    def list_workspaces(self):
        return tuple(sorted(self.workspaces.values(), key=lambda item: item.id.value))

    def update_workspace(self, workspace, *, now):
        del now
        self._called("update_workspace")
        self.workspaces[workspace.id] = workspace
        return workspace

    def register_project(self, workspace_id, manifest, *, now):
        del now
        self._called("register_project")
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def replace_project(self, workspace_id, manifest, *, now):
        del now
        self._called("replace_project")
        self.projects[(workspace_id, manifest.project.id)] = manifest
        return manifest

    def get_project(self, workspace_id, project_id):
        return self.projects.get((workspace_id, project_id))

    def list_projects(self, workspace_id):
        return tuple(
            manifest
            for (found_workspace, _project_id), manifest in sorted(
                self.projects.items(), key=lambda item: item[0][1].value
            )
            if found_workspace == workspace_id
        )

    def unregister_project(self, workspace_id, project_id):
        self._called("unregister_project")
        return self.projects.pop((workspace_id, project_id), None) is not None


class _DiscoveryAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def discover(self, body: object, *, workspace_id: str) -> dict[str, object]:
        self.calls += 1
        assert workspace_id == "workspace-a"
        assert body == {"connector_id": "http.json", "connection_ref": "conn-1"}
        return {
            "schema": "ronin.connector-discovery/v1",
            "items": [{"asset_ref": "conn-1::orders", "kind": "json", "fields": []}],
            "count": 1,
        }


class _SyncAdapter:
    def __init__(self) -> None:
        self.plans = 0

    def plan(self, body: object, *, workspace_id: str) -> dict[str, object]:
        self.plans += 1
        assert workspace_id == "workspace-a"
        assert isinstance(body, dict)
        return {"plan": {"mode": body["mode"]}}

    def validate_definition(self, body: object) -> dict[str, object]:
        assert isinstance(body, dict)
        result: dict[str, object] = {
            key: body[key]
            for key in (
                "id",
                "connector_id",
                "connection_ref",
                "asset_ref",
                "destination_ref",
                "checkpoint_identity",
                "mode",
            )
        }
        for key in ("source_revision_ref", "destination_asset_id"):
            if key in body:
                result[key] = body[key]
        return result


class _WorkerConnector:
    descriptor = ConnectorDescriptor("postgres", 1, ConnectorCapabilities(read=True))

    def read(self, connection, asset, secrets, *, limit, checkpoint):
        del connection, asset, secrets, checkpoint
        assert limit == 10_000
        return ConnectorReadResult(
            fields=(FieldSchema("id", "integer", nullable=False),),
            rows=({"id": 42},),
            checkpoint=SourceCheckpoint("cursor", "42"),
        )


class _DurableJobs:
    def __init__(self) -> None:
        self.submissions = []
        self.job = None
        self.state = "succeeded"

    def submit(self, payload: object, *, idempotency_key: str | None):
        self.submissions.append((payload, idempotency_key))
        params = payload["parameters"]
        self.job = type(
            "Job",
            (),
            {
                "id": "job-sync-1",
                "target": payload["target"],
                "project_id": payload["project"],
                "parameters_json": json.dumps(params),
            },
        )()
        return 201, {"id": "job-sync-1", "state": "queued"}

    def get_job(self, job_id: str):
        return self.job if self.job is not None and job_id == "job-sync-1" else None

    def status(self, job_id: str):
        return {"id": job_id, "state": self.state}

    def events(self, job_id: str, *, since, limit):
        del job_id, since, limit
        return {"items": [{"kind": "worker.attempt.succeeded"}], "next_since": None}

    def evidence(self, job_id: str):
        del job_id
        return {"items": [{"digest": "abc"}]}

    def cancel(self, job_id: str):
        return {"id": job_id, "state": "cancellation_requested"}


class _Workflow:
    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id

    def to_payload(self) -> dict[str, object]:
        return {"id": self.id, "name": "Demo workflow"}


class _WorkflowRun:
    def __init__(self, run_id: str) -> None:
        self.id = type("RunId", (), {"value": run_id})()

    def to_payload(self) -> dict[str, object]:
        return {"id": self.id.value, "state": "pending"}


class _TaskRun:
    id = type("TaskId", (), {"value": "task-1"})()
    workflow_run_id = type("RunId", (), {"value": "run-1"})()
    node_id = type("NodeId", (), {"value": "node-1"})()
    state = "pending"
    attempt_count = 0


class _Scheduler:
    def put_workflow(self, workspace_id, workflow):
        assert workspace_id == _WS_A
        assert workflow.id.value == "pipeline:project-1:main"
        self.pipeline_workflow = workflow
        return workflow

    def list_workflows(self, workspace_id):
        assert workspace_id == _WS_A
        return (_Workflow("workflow-1"),)

    def get_run(self, workspace_id, run_id):
        assert workspace_id == _WS_A
        return _WorkflowRun(run_id.value) if run_id.value == "run-1" else None

    def list_task_runs(self, workspace_id, run_id):
        assert workspace_id == _WS_A
        assert run_id.value == "run-1"
        return (_TaskRun(),)

    def create_workflow_run(self, workspace_id, workflow_id, trigger, *, idempotency_key):
        assert workspace_id == _WS_A
        if workflow_id.value.startswith("pipeline:"):
            assert trigger.kind == "api"
            assert idempotency_key == "pipeline:project-1:main:main/working:" + "a" * 64
            return _WorkflowRun("pipeline-run-1")
        assert workflow_id.value == "workflow-1"
        assert trigger.kind == "api"
        assert idempotency_key == "request-1"
        return _WorkflowRun("run-1")

    def cancel_workflow_run(self, workspace_id, run_id):
        assert workspace_id == _WS_A
        assert run_id.value == "run-1"
        return 2


class _Glossary:
    def __init__(self) -> None:
        self.terms = {}

    def put(self, workspace_id, term, *, now):
        del now
        self.terms[(workspace_id, str(term.id), term.version)] = term
        return term

    def list_all(self, workspace_id):
        return tuple(term for (found, _, _), term in self.terms.items() if found == workspace_id)

    def list_latest(self, workspace_id):
        return self.list_all(workspace_id)

    def search(self, workspace_id, query, *, limit=100):
        del query
        return self.list_all(workspace_id)[:limit]

    def get(self, workspace_id, term_id, version):
        return self.terms.get((workspace_id, str(term_id), version))


class _CatalogGovernance:
    def __init__(self) -> None:
        self.sensitivity = {}
        self.ownership = {}
        self.assets = {}
        self.last_asset_limit = None
        self.last_asset_cursor = None

    def list_assets(self, workspace_id, *, limit=None):
        del workspace_id
        self.last_asset_limit = limit
        return ()

    def search_assets(self, workspace_id, query, *, limit=100):
        del workspace_id, query, limit
        return ()

    def list_assets_page(self, workspace_id, *, limit=50, cursor=None):
        del workspace_id
        self.last_asset_limit = limit
        self.last_asset_cursor = cursor
        return CatalogAssetPage((), None)

    def search_assets_page(self, workspace_id, query, *, limit=50, cursor=None):
        del workspace_id, query
        self.last_asset_limit = limit
        self.last_asset_cursor = cursor
        return CatalogAssetPage((), None)

    def put_sensitivity(self, workspace_id, asset_id, metadata, *, now):
        del now
        self.sensitivity[(workspace_id, asset_id, metadata.version)] = metadata
        return metadata

    def put_ownership(self, workspace_id, asset_id, metadata, *, now):
        del now
        self.ownership[(workspace_id, asset_id, metadata.version)] = metadata
        return metadata

    def create_asset(self, workspace_id, asset, *, now):
        del now
        self.assets[(workspace_id, asset.id)] = asset
        return asset

    def replace_asset(self, workspace_id, asset, *, now):
        del now
        self.assets[(workspace_id, asset.id)] = asset
        return asset

    def upstream(self, workspace_id, ref):
        del workspace_id
        return (_LineagePayload({"direction": "upstream", "asset_id": str(ref.asset_id)}),)

    def downstream(self, workspace_id, ref):
        del workspace_id
        return (_LineagePayload({"direction": "downstream", "asset_id": str(ref.asset_id)}),)


class _LineagePayload:
    def __init__(self, payload):
        self.payload = payload

    def to_payload(self):
        return self.payload


_ACTOR = Actor(
    Principal(
        PrincipalId("principal-test"),
        "user",
        "Test User",
        "https://issuer.example.test",
        "subject-test",
    )
)


class _Authenticator:
    def authenticate(self, authorization):
        return _ACTOR if authorization == "Bearer good" else None


class _Authorizer:
    def __init__(self, allowed: set[tuple[str, str]] | None = None) -> None:
        self.allowed = allowed
        self.requirements = []
        self.unavailable = False

    def authorize(self, actor, requirement):
        assert actor == _ACTOR
        self.requirements.append(requirement)
        if self.unavailable:
            raise ControlPlaneUnavailable("dependency unavailable")
        allowed = (
            self.allowed is None
            or (str(requirement.workspace_id), requirement.permission) in self.allowed
        )
        return PolicyDecision(
            allowed,
            "allowed" if allowed else "denied",
            (requirement.permission,) if allowed else (),
        )


def _manifest(name: str = "Project", project_id: ProjectId = _PROJECT) -> ProjectManifest:
    return ProjectManifest.from_project(
        Project(
            project_id,
            name,
            (
                RepositoryBinding(
                    "code",
                    "https://git.example.test/team/project.git",
                    role="primary",
                ),
            ),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )


@contextmanager
def _server(
    store: _Store,
    authorizer: _Authorizer,
    scheduler: _Scheduler | None = None,
    plugin_host: PluginHost | None = None,
    plugin_routes_enabled: bool = False,
    studio_root: Path | None = None,
    audit_mutation=None,
    glossary_reader=None,
    catalog_reader=None,
    feature_definition_service=None,
    data_engineering_reader=None,
    ingestion_adapter=None,
    durable_jobs=None,
) -> Iterator[tuple[str, int]]:
    server = WorkspaceProjectHTTPServer(
        ("127.0.0.1", 0),
        WorkspaceService(store),
        ProjectService(store),
        authenticator=_Authenticator(),
        authorizer=authorizer,
        workflow_reader=scheduler,
        workflow_runner=scheduler,
        workflow_canceller=scheduler,
        plugin_host=plugin_host,
        plugin_routes_enabled=plugin_routes_enabled,
        studio_root=studio_root,
        audit_mutation=audit_mutation,
        glossary_reader=glossary_reader,
        catalog_reader=catalog_reader,
        feature_definition_service=feature_definition_service,
        data_engineering_reader=data_engineering_reader,
        ingestion_adapter=ingestion_adapter,
        durable_jobs=durable_jobs,
        request_timeout_seconds=1.0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield str(host), int(port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _request(
    address: tuple[str, int],
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    authorization: str | None = "Bearer good",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    conn = http.client.HTTPConnection(*address, timeout=3)
    request_headers = dict(headers or {})
    if authorization is not None:
        request_headers["Authorization"] = authorization
    if body is not None and "Content-Length" not in request_headers:
        request_headers["Content-Length"] = str(len(body))
    conn.request(method, path, body=body, headers=request_headers)
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    status = response.status
    conn.close()
    return status, payload


def _json_body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_plugin_project_route_dispatches_after_authorization() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    store.projects[(_WS_A, _PROJECT)] = _manifest()
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose(
        (PluginRecord(plugin.manifest, plugin, "test"),),
        services={
            "workspace_service": WorkspaceService(store),
            "project_service": ProjectService(store),
        },
    )
    host = PluginHost(manager, plan)
    manager.start(plan)
    try:
        with _server(
            store,
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
        ) as address:
            status, payload = _request(
                address,
                "GET",
                f"/v1/workspaces/{_WS_A}/projects?limit=1",
            )
        assert status == 200
        assert payload["items"][0]["project"]["id"] == str(_PROJECT)
        assert payload["next_cursor"] is None
    finally:
        manager.stop(plan)


def test_pipeline_run_materializes_workflow_and_validates_digest() -> None:
    store = _Store()
    authorizer = _Authorizer()
    scheduler = _Scheduler()
    with _server(store, authorizer, scheduler=scheduler) as address:
        body = {
            "revision_key": "main/working",
            "ir_digest": "a" * 64,
            "runtime": "local-preview",
            "parameters": {"pipeline": {"config": {"name": "main"}, "nodes": [], "edges": []}},
        }
        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/projects/project-1/pipelines/main/runs",
            body=_json_body(body),
        )
        assert status == 201
        assert payload["id"] == "pipeline-run-1"
        assert scheduler.pipeline_workflow.id.value == "pipeline:project-1:main"
        invalid = dict(body)
        invalid["ir_digest"] = "bad"
        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/projects/project-1/pipelines/main/runs",
            body=_json_body(invalid),
        )
        assert status == 400
        assert payload["error"]["code"] == "invalid_request"


def test_project_permission_inspection_is_resource_scoped() -> None:
    store = _Store()
    with _server(store, _Authorizer()) as address:
        status, payload = _request(
            address,
            "GET",
            "/v1/workspaces/workspace-a/projects/project-1/permissions",
        )
    assert status == 200
    assert payload["workspace_id"] == "workspace-a"
    assert payload["project_id"] == "project-1"
    assert set(payload["permissions"]) == {"project.read", "project.write", "scheduler.write"}


def test_project_permission_inspection_fails_closed_without_project_read() -> None:
    store = _Store()
    with _server(store, _Authorizer(allowed=set())) as address:
        status, payload = _request(
            address,
            "GET",
            "/v1/workspaces/workspace-a/projects/project-1/permissions",
        )
    assert status == 403
    assert payload["error"]["code"] == "forbidden"


def test_platform_capabilities_exposes_only_ready_plugin_capabilities() -> None:
    store = _Store()
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)
    host.start()
    try:
        with _server(store, _Authorizer(), plugin_host=host, plugin_routes_enabled=True) as address:
            status, payload = _request(address, "GET", "/v1/platform/capabilities")
        assert status == 200
        assert payload["workspaces.read"] == plugin.manifest.id
    finally:
        host.stop()


def test_connector_discovery_route_delegates_through_authenticated_control_plane() -> None:
    store = _Store()
    body = _json_body({"connector_id": "http.json", "connection_ref": "conn-1"})
    adapter = _DiscoveryAdapter()
    authorizer = _Authorizer()
    with _server(store, authorizer, ingestion_adapter=adapter) as address:
        status, payload = _request(
            address,
            "POST",
            "/v1/platform/connectors/discover?workspace_id=workspace-a",
            body=body,
            headers={"Content-Type": "application/json"},
        )
    assert status == 200
    assert adapter.calls == 1
    assert authorizer.requirements[-1].permission == "workspace.read"
    assert str(authorizer.requirements[-1].workspace_id) == "workspace-a"
    assert payload["schema"] == "ronin.connector-discovery/v1"
    assert payload["items"][0]["asset_ref"] == "conn-1::orders"


def test_connector_discovery_is_denied_before_adapter_side_effect() -> None:
    store = _Store()
    body = _json_body({"connector_id": "http.json", "connection_ref": "conn-1"})
    adapter = _DiscoveryAdapter()
    with _server(store, _Authorizer(allowed=set()), ingestion_adapter=adapter) as address:
        status, payload = _request(
            address,
            "POST",
            "/v1/platform/connectors/discover?workspace_id=workspace-a",
            body=body,
            headers={"Content-Type": "application/json"},
        )
    assert status == 403
    assert payload["error"]["code"] == "forbidden"
    assert adapter.calls == 0


def test_connector_sync_submits_validated_idempotent_durable_job_and_reads_evidence() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    store.workspaces[_WS_B] = Workspace(_WS_B, "B")
    store.projects[(_WS_A, _PROJECT)] = _manifest()
    project_b = ProjectId("project-2")
    store.projects[(_WS_A, project_b)] = _manifest("Project B", project_b)
    store.projects[(_WS_B, _PROJECT)] = _manifest()
    adapter = _SyncAdapter()
    jobs = _DurableJobs()
    definition = {
        "id": "orders-sync",
        "connector_id": "postgres",
        "connection_ref": "conn-1",
        "asset_ref": "conn-1::public.orders",
        "destination_ref": "asset://warehouse/orders",
        "checkpoint_identity": "orders-v1",
        "mode": "incremental",
        "source_revision_ref": {
            "asset_id": "source-orders",
            "version": "source-v1",
        },
        "destination_asset_id": "target-orders",
    }
    source_ref = AssetRef(AssetId("source-orders"), AssetVersion("source-v1"))

    class Catalog:
        def get_revision(self, workspace_id, ref):
            return object() if workspace_id == _WS_A and ref == source_ref else None

        def get_asset(self, workspace_id, asset_id):
            if workspace_id != _WS_A:
                return None
            if asset_id == source_ref.asset_id:
                return CatalogAsset(
                    asset_id,
                    "table",
                    "Source orders",
                    properties=(
                        ("ronin.connector_id", "postgres"),
                        ("ronin.connection_ref", "conn-1"),
                        ("ronin.asset_ref", "public.orders"),
                    ),
                )
            if asset_id == AssetId("target-orders"):
                return CatalogAsset(asset_id, "table", "Target orders")
            return None

        def downstream_for_execution(self, workspace_id, ref, execution_ref, *, limit=100):
            del workspace_id, ref, execution_ref, limit
            return ()

    with _server(
        store,
        _Authorizer(),
        ingestion_adapter=adapter,
        durable_jobs=jobs,
        catalog_reader=Catalog(),
    ) as address:
        status, submitted = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=_json_body({"project_id": "project-1", "definition": definition}),
            headers={"Idempotency-Key": "orders-sync-once"},
        )
        assert status == 201
        assert submitted == {"id": "job-sync-1", "state": "queued"}
        payload, key = jobs.submissions[0]
        assert key == "orders-sync-once"
        assert payload["target"] == "connector.sync.v1"
        assert payload["parameters"] == {
            "workspace_id": "workspace-a",
            "connector_id": "postgres",
            "source_ref": "conn-1::public.orders",
            "destination_ref": "asset://warehouse/orders",
            "checkpoint_ref": "orders-v1",
            "mode": "incremental",
            "source_revision_ref": source_ref.to_payload(),
            "destination_asset_id": "target-orders",
        }
        status, result = _request(
            address,
            "GET",
            "/v1/platform/connectors/syncs/job-sync-1/status?workspace_id=workspace-a&project_id=project-1",
        )
        cancel_status, cancellation = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs/job-sync-1/cancel?workspace_id=workspace-a&project_id=project-1",
            body=_json_body({}),
        )
        foreign_status, foreign = _request(
            address,
            "GET",
            "/v1/platform/connectors/syncs/job-sync-1/status?workspace_id=workspace-b&project_id=project-1",
        )
        foreign_cancel_status, foreign_cancel = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs/job-sync-1/cancel?workspace_id=workspace-b&project_id=project-1",
            body=_json_body({}),
        )
        wrong_project_status, wrong_project = _request(
            address,
            "GET",
            "/v1/platform/connectors/syncs/job-sync-1/status?workspace_id=workspace-a&project_id=project-2",
        )
        jobs.state = "failed"
        failed_status, failed_result = _request(
            address,
            "GET",
            "/v1/platform/connectors/syncs/job-sync-1/status?workspace_id=workspace-a&project_id=project-1",
        )
    assert status == 200
    assert result["job"]["state"] == "succeeded"
    assert result["events"]["items"][0]["kind"] == "worker.attempt.succeeded"
    assert result["evidence"]["items"][0]["digest"] == "abc"
    assert cancel_status == 200
    assert cancellation["state"] == "cancellation_requested"
    assert foreign_status == 404
    assert foreign["error"]["code"] == "not_found"
    assert foreign_cancel_status == 404
    assert foreign_cancel["error"]["code"] == "not_found"
    assert wrong_project_status == 404
    assert wrong_project["error"]["code"] == "not_found"
    assert failed_status == 200
    assert failed_result["lineage"] == {
        "status": "not_recorded",
        "items": [],
        "truncated": False,
    }
    assert adapter.plans == 1


def test_governed_connector_sync_validates_and_persists_catalog_refs() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    store.projects[(_WS_A, _PROJECT)] = _manifest()
    source_ref = AssetRef.from_payload({"asset_id": "source", "version": "source-v1"})

    class Catalog:
        def __init__(self, physical_asset_ref="public.orders"):
            self.physical_asset_ref = physical_asset_ref

        def get_revision(self, workspace_id, ref):
            assert workspace_id == _WS_A
            return object() if ref == source_ref else None

        def get_asset(self, workspace_id, asset_id):
            assert workspace_id == _WS_A
            if asset_id == source_ref.asset_id:
                return CatalogAsset(
                    asset_id,
                    "table",
                    "Source",
                    properties=(
                        ("ronin.connector_id", "postgres"),
                        ("ronin.connection_ref", "conn-1"),
                        ("ronin.asset_ref", self.physical_asset_ref),
                    ),
                )
            if asset_id == AssetId("target"):
                return CatalogAsset(asset_id, "table", "Target")
            return None

    definition = {
        "id": "governed-sync",
        "connector_id": "postgres",
        "connection_ref": "conn-1",
        "asset_ref": "conn-1::public.orders",
        "destination_ref": "artifact://warehouse/orders",
        "checkpoint_identity": "orders-v1",
        "mode": "snapshot",
        "source_revision_ref": source_ref.to_payload(),
        "destination_asset_id": "target",
    }
    jobs = _DurableJobs()
    with _server(
        store,
        _Authorizer(),
        ingestion_adapter=_SyncAdapter(),
        durable_jobs=jobs,
        catalog_reader=Catalog(),
    ) as address:
        status, _ = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=_json_body({"project_id": "project-1", "definition": definition}),
            headers={"Idempotency-Key": "governed-sync-once"},
        )
    assert status == 201
    parameters = jobs.submissions[0][0]["parameters"]
    assert parameters["source_revision_ref"] == source_ref.to_payload()
    assert parameters["destination_asset_id"] == "target"

    rejected_jobs = _DurableJobs()
    with _server(
        store,
        _Authorizer(),
        ingestion_adapter=_SyncAdapter(),
        durable_jobs=rejected_jobs,
        catalog_reader=Catalog("public.other"),
    ) as address:
        mismatch_status, mismatch = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=_json_body({"project_id": "project-1", "definition": definition}),
            headers={"Idempotency-Key": "mismatched-source"},
        )
        missing_definition = {
            **definition,
            "source_revision_ref": {"asset_id": "missing", "version": "v0"},
        }
        missing_status, missing = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=_json_body({"project_id": "project-1", "definition": missing_definition}),
            headers={"Idempotency-Key": "missing-source-revision"},
        )
    assert mismatch_status == 400
    assert "not bound" in mismatch["error"]["message"]
    assert missing_status == 400
    assert "does not identify" in missing["error"]["message"]
    assert rejected_jobs.submissions == []


def test_connector_sync_rejects_scope_and_missing_idempotency_before_job_creation() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    store.projects[(_WS_A, _PROJECT)] = _manifest()
    adapter = _SyncAdapter()
    jobs = _DurableJobs()
    body = _json_body(
        {
            "project_id": "project-1",
            "definition": {
                "id": "orders-sync",
                "connector_id": "postgres",
                "connection_ref": "conn-1",
                "asset_ref": "other-connection::public.orders",
                "destination_ref": "target",
                "checkpoint_identity": "orders-v1",
                "mode": "snapshot",
            },
        }
    )
    with _server(store, _Authorizer(), ingestion_adapter=adapter, durable_jobs=jobs) as address:
        status, payload = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=body,
            headers={"Idempotency-Key": "bad-source"},
        )
        assert status == 400
        assert payload["error"]["code"] == "invalid_request"
        status, payload = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=body,
        )
        assert status == 400
        assert payload["error"]["code"] == "invalid_request"
        assert jobs.submissions == []
        assert adapter.plans == 0


def test_connector_sync_authorization_precedes_definition_validation_and_job_creation() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    adapter = _SyncAdapter()
    jobs = _DurableJobs()
    with _server(
        store,
        _Authorizer(allowed={("workspace-a", "workspace.read")}),
        ingestion_adapter=adapter,
        durable_jobs=jobs,
    ) as address:
        status, payload = _request(
            address,
            "POST",
            "/v1/platform/connectors/syncs?workspace_id=workspace-a",
            body=_json_body({"broken": True}),
            headers={"Idempotency-Key": "denied"},
        )
    assert status == 403
    assert payload["error"]["code"] == "forbidden"
    assert adapter.plans == 0
    assert jobs.submissions == []


def test_connector_sync_is_persisted_by_the_real_durable_job_service(tmp_path: Path) -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    store.projects[(_WS_A, _PROJECT)] = _manifest()
    paths = WorkerPaths(tmp_path / "workspace", tmp_path / "data")
    database = paths.data_dir / "ronin.sqlite3"
    checkpoint_store = SqliteConnectorCheckpointStore(database)
    now = Instant(_NOW)
    SqliteWorkspaceStore(database, migration_now=now).create_workspace(
        Workspace(_WS_A, "A"), now=now
    )
    catalog = SqliteCatalogStore(database, migration_now=now)
    source_catalog_id = AssetId("connector-source-orders")
    destination_catalog_id = AssetId("connector-target-orders")
    source_catalog_ref = AssetRef(source_catalog_id, AssetVersion("source-v1"))
    catalog.create_asset(
        _WS_A,
        CatalogAsset(
            source_catalog_id,
            "table",
            "Source orders",
            properties=(
                ("ronin.connector_id", "postgres"),
                ("ronin.connection_ref", "conn-1"),
                ("ronin.asset_ref", "public.orders"),
            ),
        ),
        now=now,
    )
    catalog.create_asset(
        _WS_A, CatalogAsset(destination_catalog_id, "table", "Target orders"), now=now
    )
    catalog.put_revision(_WS_A, AssetRevision(source_catalog_ref), now=now)
    artifacts = LocalArtifactStore(paths.data_dir / "artifacts")
    application = DurableHTTPApplication(
        DurableExecutionService(
            SqliteJobStore(database, migration_now=_NOW),
        )
    )
    definition = {
        "id": "orders-sync",
        "connector_id": "postgres",
        "connection_ref": "conn-1",
        "asset_ref": "conn-1::public.orders",
        "destination_ref": "asset://warehouse/orders",
        "checkpoint_identity": "orders-v1",
        "mode": "snapshot",
        "source_revision_ref": source_catalog_ref.to_payload(),
        "destination_asset_id": str(destination_catalog_id),
    }
    try:
        with _server(
            store,
            _Authorizer(),
            ingestion_adapter=_SyncAdapter(),
            durable_jobs=application,
            catalog_reader=catalog,
        ) as address:
            first_status, first = _request(
                address,
                "POST",
                "/v1/platform/connectors/syncs?workspace_id=workspace-a",
                body=_json_body({"project_id": "project-1", "definition": definition}),
                headers={"Idempotency-Key": "real-orders-sync"},
            )
            retry_status, retry = _request(
                address,
                "POST",
                "/v1/platform/connectors/syncs?workspace_id=workspace-a",
                body=_json_body({"project_id": "project-1", "definition": definition}),
                headers={"Idempotency-Key": "real-orders-sync"},
            )
            registry = ConnectorRegistry((_WorkerConnector(),))
            sync_service = IngestionSyncService(registry, checkpoint_store)

            async def execute_durable_job() -> str:
                config = LocalWorkerRuntimeConfig(
                    paths=paths,
                    owner="connector-sync-integration-worker",
                    image=f"sha256:{'a' * 64}",
                    database_name="ronin.sqlite3",
                    connector_sync_service=sync_service,
                    connector_connection=lambda workspace_id, connection_ref: (
                        workspace_id,
                        connection_ref,
                    ),
                    connector_asset=lambda connection, asset_ref: AssetHandle(
                        ConnectionId(connection[1]),
                        tuple(asset_ref.split(".")[:-1]),
                        asset_ref.split(".")[-1],
                    ),
                    connector_secrets=object(),
                    connector_destination=ArtifactDestinationWriter(artifacts),
                )
                async with LocalWorkerRuntime(
                    config,
                    migration_now=Instant(_NOW),
                    artifact_store=artifacts,
                ) as runtime:
                    outcome = await runtime.run_once(
                        attempt_id=AttemptId("attempt-connector-sync-real"),
                        lease_token=LeaseToken("lease-connector-sync-real"),
                    )
                assert outcome.execution is not None
                return outcome.execution.state.value

            worker_state = asyncio.run(execute_durable_job())
            status, job = _request(
                address,
                "GET",
                f"/v1/platform/connectors/syncs/{first['id']}/status?workspace_id=workspace-a&project_id=project-1",
            )
        assert first_status == 201
        assert retry_status == 200
        assert retry["id"] == first["id"]
        assert status == 200
        assert worker_state == "succeeded"
        assert job["job"]["state"] == "succeeded"
        assert job["evidence"]["items"]
        assert checkpoint_store.get("workspace-a/orders-v1") == SourceCheckpoint("cursor", "42")
        destination_revisions = catalog.list_revisions(_WS_A, destination_catalog_id)
        assert len(destination_revisions) == 1
        lineage = catalog.upstream(_WS_A, destination_revisions[0].ref)
        assert len(lineage) == 1
        assert lineage[0].source == source_catalog_ref
        assert lineage[0].mode == "observed"
        assert job["lineage"] == {
            "status": "available",
            "items": [lineage[0].to_payload()],
            "truncated": False,
        }
        assert lineage[0].execution_ref == application.run_id_for_job(first["id"])
    finally:
        application.close()


def test_platform_ui_manifest_exposes_ready_plugin_navigation() -> None:
    store = _Store()
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)
    host.start()
    try:
        with _server(store, _Authorizer(), plugin_host=host) as address:
            status, payload = _request(address, "GET", "/v1/platform/ui-manifest")
        assert status == 200
        assert payload["items"][0]["plugin_id"] == plugin.manifest.id
        assert payload["items"][0]["manifest"]["navigation"][0]["id"] == "workspaces"
    finally:
        host.stop()


def test_local_observability_plugins_are_readable_over_control_plane() -> None:
    store = _Store()
    buffer = LocalObservabilityBuffer()
    logging_plugin = LoggingPlugin(buffer)
    monitoring_plugin = MonitoringPlugin(buffer)
    manager = PluginManager()
    plan = manager.compose(
        (
            PluginRecord(logging_plugin.manifest, logging_plugin, "test"),
            PluginRecord(monitoring_plugin.manifest, monitoring_plugin, "test"),
        ),
        services={"observability_buffer": buffer},
    )
    host = PluginHost(manager, plan)
    host.start()
    buffer.log("info", "local event", logging_plugin.manifest.id, {"token": "secret"})
    buffer.metric("ronin.test.requests", 1, monitoring_plugin.manifest.id)
    try:
        with _server(store, _Authorizer(), plugin_host=host, plugin_routes_enabled=True) as address:
            logs_status, logs = _request(address, "GET", "/v1/platform/logs")
            metrics_status, metrics = _request(address, "GET", "/v1/platform/metrics")
        assert logs_status == 200
        assert metrics_status == 200
        redacted_token = logs["items"][0]["attributes"]["token"]
        assert redacted_token == "[REDACTED]"  # noqa: S105
        assert metrics["items"][0]["name"] == "ronin.test.requests"
    finally:
        host.stop()


def test_plugin_project_create_requires_idempotency_and_registers_via_port() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose(
        (PluginRecord(plugin.manifest, plugin, "test"),),
        services={
            "workspace_service": WorkspaceService(store),
            "project_service": ProjectService(store),
        },
    )
    host = PluginHost(manager, plan)
    manager.start(plan)
    try:
        with _server(
            store,
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
        ) as address:
            status, payload = _request(
                address,
                "POST",
                f"/v1/workspaces/{_WS_A}/projects",
                body=_json_body(_manifest().to_data()),
                headers={"Idempotency-Key": "project-create-1"},
            )
        assert status == 200
        assert payload["project"]["id"] == str(_PROJECT)
        assert store.calls["register_project"] == 1
    finally:
        manager.stop(plan)


def test_plugin_project_mutation_fails_closed_when_audit_hook_is_unavailable() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose(
        (PluginRecord(plugin.manifest, plugin, "test"),),
        services={
            "workspace_service": WorkspaceService(store),
            "project_service": ProjectService(store),
        },
    )
    host = PluginHost(manager, plan)
    manager.start(plan)
    try:

        def fail_audit(actor, action, workspace_id, metadata):
            del actor, action, workspace_id, metadata
            raise RuntimeError("audit store unavailable")

        with _server(
            store,
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
            audit_mutation=fail_audit,
        ) as address:
            status, payload = _request(
                address,
                "POST",
                f"/v1/workspaces/{_WS_A}/projects",
                body=_json_body(_manifest().to_data()),
                headers={"Idempotency-Key": "audit-fail-1"},
            )
        assert status == 503
        assert payload["error"]["code"] == "mutation_audit_unavailable"
        assert store.calls.get("register_project", 0) == 0
    finally:
        manager.stop(plan)


def test_glossary_term_can_be_published_through_authenticated_route() -> None:
    store = _Store()
    glossary = _Glossary()
    term = GlossaryTerm(
        GlossaryTermId("customer"),
        "1",
        "Customer",
        "A customer account",
        "data-governance",
    )
    with _server(store, _Authorizer(), glossary_reader=glossary) as address:
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/glossary/terms",
            body=_json_body(term.to_payload()),
        )
        assert status == 201, payload
        assert payload == term.to_payload()
        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/glossary/terms/customer/1",
        )
    assert status == 200
    assert payload == term.to_payload()


def test_catalog_governance_metadata_can_be_published_through_authenticated_routes() -> None:
    store = _Store()
    catalog = _CatalogGovernance()
    sensitivity = SensitivityMetadata(1, explicit=("pii",))
    ownership = OwnershipMetadata(1, "group/data", ("user/steward",), "sales", "active")
    with _server(store, _Authorizer(), catalog_reader=catalog) as address:
        for suffix, metadata in (("sensitivity", sensitivity), ("ownership", ownership)):
            status, payload = _request(
                address,
                "POST",
                f"/v1/workspaces/{_WS_A}/catalog/assets/asset-1/{suffix}",
                body=_json_body(metadata.to_payload()),
            )
            assert status == 201
            assert payload == metadata.to_payload()
    assert catalog.sensitivity[(_WS_A, AssetId("asset-1"), 1)] == sensitivity
    assert catalog.ownership[(_WS_A, AssetId("asset-1"), 1)] == ownership


def test_catalog_asset_create_and_replace_routes_validate_path_identity() -> None:
    store = _Store()
    catalog = _CatalogGovernance()
    asset = CatalogAsset(AssetId("asset-1"), "dataset", "Customers")
    replacement = CatalogAsset(AssetId("asset-1"), "dataset", "Customers v2")
    with _server(store, _Authorizer(), catalog_reader=catalog) as address:
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/catalog/assets",
            body=_json_body(asset.to_payload()),
        )
        assert status == 201
        assert payload == asset.to_payload()
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/catalog/assets/asset-1",
            body=_json_body(replacement.to_payload()),
        )
        assert status == 200
        assert payload == replacement.to_payload()
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/catalog/assets/other",
            body=_json_body(replacement.to_payload()),
        )
    assert status == 400
    assert payload["error"]["code"] == "invalid_request"


def test_catalog_asset_listing_passes_the_http_bound_to_storage() -> None:
    store = _Store()
    catalog = _CatalogGovernance()
    with _server(store, _Authorizer(), catalog_reader=catalog) as address:
        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/catalog/assets?limit=17",
        )
    assert status == 200
    assert payload == {"items": [], "next_cursor": None}
    assert catalog.last_asset_limit == 17


def test_catalog_asset_listing_passes_cursor_and_rejects_invalid_query() -> None:
    store = _Store()
    catalog = _CatalogGovernance()
    with _server(store, _Authorizer(), catalog_reader=catalog) as address:
        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/catalog/assets?q=orders&limit=9&cursor=opaque",
        )
        assert status == 200
        assert payload == {"items": [], "next_cursor": None}
        assert catalog.last_asset_cursor == "opaque"

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/catalog/assets?limit=9&limit=10",
        )
    assert status == 400
    assert payload["error"]["message"] == "catalog query parameters are invalid"


def test_catalog_lineage_route_requires_explicit_supported_direction() -> None:
    store = _Store()
    catalog = _CatalogGovernance()
    with _server(store, _Authorizer(), catalog_reader=catalog) as address:
        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/catalog/lineage/asset-1/v1?direction=downstream",
        )
        assert status == 200
        assert payload == {"items": [{"direction": "downstream", "asset_id": "asset-1"}]}
        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/catalog/lineage/asset-1/v1?direction=sideways",
        )
    assert status == 400
    assert payload["error"]["code"] == "invalid_request"


def test_plugin_project_read_replace_delete_routes_use_project_port() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    store.projects[(_WS_A, _PROJECT)] = _manifest()
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose(
        (PluginRecord(plugin.manifest, plugin, "test"),),
        services={
            "workspace_service": WorkspaceService(store),
            "project_service": ProjectService(store),
        },
    )
    host = PluginHost(manager, plan)
    manager.start(plan)
    try:
        with _server(
            store,
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
        ) as address:
            status, payload = _request(
                address, "GET", f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}"
            )
            assert status == 200
            assert payload["project"]["id"] == str(_PROJECT)

            status, payload = _request(
                address,
                "PUT",
                f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
                body=_json_body(_manifest("Updated").to_data()),
            )
            assert status == 200
            assert payload["project"]["name"] == "Updated"

            status, payload = _request(
                address, "DELETE", f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}"
            )
            assert status == 200
            assert payload == {"unregistered": True, "project_id": str(_PROJECT)}
    finally:
        manager.stop(plan)


def test_workflow_routes_fail_closed_when_scheduler_is_not_configured() -> None:
    assert {
        ("GET", "/v1/workspaces/{workspace_id}/workflows"),
        ("POST", "/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs"),
        ("GET", "/v1/workspaces/{workspace_id}/workflow-runs/{run_id}"),
        ("POST", "/v1/workspaces/{workspace_id}/workflow-runs/{run_id}/cancel"),
    } <= CONTROL_PLANE_ROUTES
    store = _Store()
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        status, payload = _request(address, "GET", "/v1/workspaces/workspace-a/workflows")
        assert status == 503
        assert payload["error"]["code"] == "scheduler_unavailable"
        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/projects/project-1/sql/query",
            body=_json_body({"sql": "SELECT 1"}),
        )
        assert status == 503
        assert payload["error"]["code"] == "sql_unavailable"
        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/workflows/workflow-1/runs",
            body=_json_body(
                {
                    "trigger": {"kind": "api", "key": "run-1", "source_ref": None},
                    "idempotency_key": "request-1",
                }
            ),
        )
        assert status == 503
        assert payload["error"]["code"] == "scheduler_unavailable"


def test_scheduler_routes_list_start_read_and_cancel() -> None:
    store = _Store()
    authorizer = _Authorizer()
    scheduler = _Scheduler()
    with _server(store, authorizer, scheduler) as address:
        status, payload = _request(address, "GET", "/v1/workspaces/workspace-a/workflows?limit=10")
        assert status == 200
        assert payload["items"] == [{"id": "workflow-1", "name": "Demo workflow"}]

        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/workflows/workflow-1/runs",
            body=_json_body(
                {
                    "trigger": {"kind": "api", "key": "run-1", "source_ref": None},
                    "idempotency_key": "request-1",
                }
            ),
        )
        assert status == 201
        assert payload["id"] == "run-1"

        status, payload = _request(address, "GET", "/v1/workspaces/workspace-a/workflow-runs/run-1")
        assert status == 200
        assert payload["tasks"] == [
            {
                "id": "task-1",
                "workflow_run_id": "run-1",
                "node_id": "node-1",
                "state": "pending",
                "attempt_count": 0,
            }
        ]

        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/workflow-runs/run-1/cancel",
        )
        assert status == 200
        assert payload == {"workflow_run_id": "run-1", "cancelled_jobs": 2}


def test_scheduler_route_with_unsupported_method_is_not_method_not_found() -> None:
    store = _Store()
    authorizer = _Authorizer()
    scheduler = _Scheduler()
    with _server(store, authorizer, scheduler) as address:
        status, payload = _request(
            address,
            "PUT",
            "/v1/workspaces/workspace-a/workflows",
            body=_json_body({}),
        )
        assert status == 405
        assert payload["error"]["code"] == "method_not_allowed"


def test_workflow_cancellation_fails_closed_when_audit_is_unavailable() -> None:
    store = _Store()
    scheduler = _Scheduler()

    def fail_audit(actor, action, workspace_id, metadata):
        del actor, action, workspace_id, metadata
        raise RuntimeError("audit unavailable")

    with _server(store, _Authorizer(), scheduler, audit_mutation=fail_audit) as address:
        status, payload = _request(
            address,
            "POST",
            "/v1/workspaces/workspace-a/workflow-runs/run-1/cancel",
        )
    assert status == 503
    assert payload["error"]["code"] == "mutation_audit_unavailable"


def test_authentication_and_denial_are_stable_json() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer(set())
    with _server(store, authorizer) as address:
        status, payload = _request(address, "GET", f"/v1/workspaces/{_WS_A}", authorization=None)
        assert status == 401
        assert payload["error"]["code"] == "unauthorized"

        status, payload = _request(address, "GET", f"/v1/workspaces/{_WS_A}")
        assert status == 403
        assert payload["error"]["code"] == "forbidden"
        assert authorizer.requirements[-1].permission == "workspace.read"


def test_workspace_list_filters_before_pagination() -> None:
    store = _Store()
    for workspace_id in (_WS_A, _WS_B, _WS_C):
        store.workspaces[workspace_id] = Workspace(workspace_id, workspace_id.value)
    authorizer = _Authorizer(
        {
            (str(_WS_A), "workspace.read"),
            (str(_WS_C), "workspace.read"),
        }
    )
    with _server(store, authorizer) as address:
        status, first = _request(address, "GET", "/v1/workspaces?limit=1")
        assert status == 200
        assert [item["id"] for item in first["items"]] == [str(_WS_A)]
        assert first["next_cursor"] is not None
        assert str(_WS_B) not in json.dumps(first)

        status, second = _request(
            address,
            "GET",
            f"/v1/workspaces?limit=1&cursor={first['next_cursor']}",
        )
        assert status == 200
        assert [item["id"] for item in second["items"]] == [str(_WS_C)]
        assert second["next_cursor"] is None


def test_workspace_update_archive_and_method_mapping() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A", "before")
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        status, updated = _request(
            address,
            "PATCH",
            f"/v1/workspaces/{_WS_A}",
            body=_json_body({"name": "Renamed", "description": "after"}),
        )
        assert status == 200
        assert updated["name"] == "Renamed"
        assert authorizer.requirements[-1].permission == "workspace.admin"

        status, archived = _request(address, "POST", f"/v1/workspaces/{_WS_A}/archive")
        assert status == 200
        assert archived["state"] == "archived"

        status, payload = _request(address, "POST", f"/v1/workspaces/{_WS_A}")
        assert status == 405
        assert payload["error"]["code"] == "method_not_allowed"

        status, payload = _request(
            address,
            "PATCH",
            f"/v1/workspaces/{_WS_A}",
            body=_json_body({"name": "Blocked", "description": None}),
        )
        assert status == 409
        assert payload["error"]["code"] == "conflict"


def test_project_http_lifecycle_uses_canonical_manifest_and_resource_ref() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer()
    original = _manifest()
    changed = _manifest("Changed")
    with _server(store, authorizer) as address:
        status, created = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/projects",
            body=original.to_json().encode("utf-8"),
        )
        assert status == 201
        assert created == original.to_data()
        assert store.calls["register_project"] == 1
        assert authorizer.requirements[-1].permission == "project.write"

        status, found = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
        )
        assert status == 200
        assert found == original.to_data()
        assert authorizer.requirements[-1].resource_ref == str(_PROJECT)

        status, listed = _request(address, "GET", f"/v1/workspaces/{_WS_A}/projects?limit=1")
        assert status == 200
        assert listed["items"] == [original.to_data()]

        status, replaced = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
            body=changed.to_json().encode("utf-8"),
        )
        assert status == 200
        assert replaced == changed.to_data()
        assert store.calls["replace_project"] == 1

        status, deleted = _request(
            address,
            "DELETE",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
        )
        assert status == 200
        assert deleted == {"unregistered": True, "project_id": str(_PROJECT)}
        assert store.calls["unregister_project"] == 1

        status, payload = _request(
            address,
            "GET",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
        )
        assert status == 404
        assert payload["error"]["code"] == "not_found"


def test_denied_and_unavailable_mutations_fail_before_body_parse_or_store_write() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    denied = _Authorizer(set())
    with _server(store, denied) as address:
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/projects",
            body=b"{not-json",
        )
        assert status == 403
        assert payload["error"]["code"] == "forbidden"
        assert store.calls.get("register_project", 0) == 0

    unavailable = _Authorizer()
    unavailable.unavailable = True
    with _server(store, unavailable) as address:
        status, payload = _request(
            address,
            "PATCH",
            f"/v1/workspaces/{_WS_A}",
            body=b"{not-json",
        )
        assert status == 503
        assert payload["error"]["code"] == "authorization_unavailable"
        assert store.calls.get("update_workspace", 0) == 0


def test_invalid_shapes_query_cursor_and_project_id_mismatch_are_400() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        cases = [
            ("GET", "/v1/workspaces?limit=101", None),
            ("GET", "/v1/workspaces?cursor=invalid", None),
            (
                "PATCH",
                f"/v1/workspaces/{_WS_A}?unexpected=1",
                _json_body({"name": "A", "description": None}),
            ),
            (
                "PATCH",
                f"/v1/workspaces/{_WS_A}",
                _json_body({"name": "A", "description": None, "extra": True}),
            ),
        ]
        for method, path, body in cases:
            status, payload = _request(address, method, path, body=body)
            assert status == 400
            assert payload["error"]["code"] == "invalid_request"

        other = ProjectManifest.from_project(
            Project(
                ProjectId("project-other"),
                "Other",
                (RepositoryBinding("code", "https://git.example.test/other.git", role="primary"),),
                ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
            )
        )
        store.projects[(_WS_A, _PROJECT)] = _manifest()
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
            body=other.to_json().encode("utf-8"),
        )
        assert status == 400
        assert payload["error"]["code"] == "invalid_request"
        assert store.calls.get("replace_project", 0) == 0


def test_missing_and_archived_project_mutations_map_to_stable_errors() -> None:
    store = _Store()
    store.workspaces[_WS_A] = Workspace(_WS_A, "A")
    authorizer = _Authorizer()
    with _server(store, authorizer) as address:
        status, payload = _request(
            address,
            "PUT",
            f"/v1/workspaces/{_WS_A}/projects/{_PROJECT}",
            body=_manifest().to_json().encode("utf-8"),
        )
        assert status == 404
        assert payload["error"]["code"] == "not_found"

        store.workspaces[_WS_A] = Workspace(_WS_A, "A", state="archived")
        status, payload = _request(
            address,
            "POST",
            f"/v1/workspaces/{_WS_A}/projects",
            body=_manifest().to_json().encode("utf-8"),
        )
        assert status == 409
        assert payload["error"]["code"] == "conflict"
        assert store.calls.get("register_project", 0) == 0


def test_govern_studio_routes_execute_through_real_http_server() -> None:
    store = _Store()
    plugin = SyntheticDataStudioPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)
    manager.start(plan)
    body = _json_body(
        {
            "plan": {
                "seed": 7,
                "tables": [
                    {
                        "name": "customers",
                        "rows": 2,
                        "primary_key": "id",
                        "columns": [{"name": "id", "kind": "integer", "nullable": False}],
                    }
                ],
            }
        }
    )
    try:
        with _server(store, _Authorizer(), plugin_host=host, plugin_routes_enabled=True) as address:
            status, generated = _request(
                address,
                "POST",
                "/v1/synthetic-data-studio/generate?workspace_id=workspace-a",
                body=body,
            )
            assert status == 200
            assert generated["status"] == "generated"
            run_id = generated["run_id"]
            status, validated = _request(
                address,
                "POST",
                "/v1/synthetic-data-studio/validate?workspace_id=workspace-a",
                body=_json_body({"plan": json.loads(body)["plan"], "run_id": run_id}),
            )
            assert status == 200
            assert validated["status"] == "validated"
            status, exported = _request(
                address,
                "POST",
                "/v1/synthetic-data-studio/export?workspace_id=workspace-a",
                body=_json_body({"run_id": run_id, "format_id": "jsonl", "table": "customers"}),
            )
            assert status == 200
            assert exported["contract"] == "synthetic-data-studio/export/v1"
    finally:
        manager.stop(plan)
