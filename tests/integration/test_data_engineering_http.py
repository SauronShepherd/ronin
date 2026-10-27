from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from studio_core import ProjectId, Workspace, WorkspaceId
from studio_core.ir import Node, OperatorRef, Port
from studio_core.plugins import PluginManager, PluginRecord
from studio_data_engineering import (
    DataEnginerringStudioPlugin,
    QueryEngineRuntimeProvider,
    SqliteQueryEvidenceReferenceStore,
)
from studio_plugin_workspaces import WorkspacesPlugin
from studio_query_engine import (
    CancellationResult,
    DiscoveredEngine,
    EngineCapabilities,
    EngineHandshake,
    QueryExecutionPolicy,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryStatus,
)
from studio_runtime import PluginHost
from studio_storage import LocalArtifactStore
from test_workspace_project_http_api import _Authorizer, _manifest, _server, _Store


def _request(
    address: tuple[str, int], method: str, path: str, body: object | None = None
) -> tuple[int, dict[str, object]]:
    import http.client

    connection = http.client.HTTPConnection(*address, timeout=3)
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Authorization": "Bearer good"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(payload))
    connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    value = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, value


class _PipelineWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def import_sdp(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        source = kwargs["source"]
        return SimpleNamespace(
            project_id=kwargs["project_id"],
            pipeline_id=kwargs["pipeline_id"],
            revision=1,
            source_digest=source.source_digest,
            metadata_artifact=SimpleNamespace(storage_ref="artifact://metadata"),
        )


class _QueryFluxTransport:
    def __init__(self) -> None:
        self.submitted = 0

    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]:
        del request
        self.submitted += 1
        return QueryHandle("query-1", "queryflux", "provider-query-1"), "next"

    def poll(self, handle: QueryHandle, next_uri: str):
        del next_uri
        return (
            QueryStatus("succeeded", provider_query_id=handle.provider_query_id),
            QueryResultPage(("value",), ((1,),)),
            None,
        )

    def cancel(self, handle: QueryHandle) -> CancellationResult:
        del handle
        return CancellationResult(False, "succeeded")


def test_data_engineering_routes_execute_through_real_control_plane() -> None:
    plugin = DataEnginerringStudioPlugin()
    manager = PluginManager()
    dependency = WorkspacesPlugin()
    plan = manager.compose(
        (
            PluginRecord(dependency.manifest, dependency, "test"),
            PluginRecord(plugin.manifest, plugin, "test"),
        )
    )
    host = PluginHost(manager, plan)
    host.start()
    pipeline = {
        "version": 1,
        "id": "http-e2e",
        "name": "HTTP E2E",
        "config": {"name": "orders"},
        "nodes": [
            {
                "id": "source",
                "instance_key": "source",
                "operator": {"name": "source.fixture", "version": 1},
                "params": {"fixture": "orders"},
                "inputs": [],
                "outputs": [{"name": "out", "kind": "batch", "schema": None}],
                "origin": {"view": "graph", "reference": None},
                "ownership": "GRAPH",
                "label": None,
            }
        ],
        "edges": [],
    }
    pipeline["nodes"][0]["id"] = Node.create(
        operator=OperatorRef("source.fixture"),
        instance_key="source",
        params={"fixture": "orders"},
        outputs=(Port("out"),),
    ).id.value
    try:
        with _server(
            _Store(),
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
            studio_root=Path(__file__).parents[2] / "web",
        ) as address:
            import http.client

            asset_connection = http.client.HTTPConnection(*address, timeout=3)
            asset_connection.request("GET", "/studio/data-enginerring-studio.html?e2e=1")
            asset_response = asset_connection.getresponse()
            asset_body = asset_response.read().decode("utf-8")
            asset_connection.close()
            health_status, health = _request(
                address, "GET", "/v1/data-engineering/health?workspace_id=workspace-a"
            )
            validate_status, validation = _request(
                address,
                "POST",
                "/v1/data-engineering/pipelines/validate?workspace_id=workspace-a",
                {"pipeline": pipeline, "runtime": "local-preview"},
            )
            preview_status, preview = _request(
                address,
                "POST",
                "/v1/data-engineering/pipelines/preview?workspace_id=workspace-a",
                {
                    "pipeline": pipeline,
                    "fixtures": {"orders": [{"amount": 1}]},
                    "row_limit": 10,
                },
            )
            assert asset_response.status == 200
            assert "Data Engineering Studio" in asset_body
            assert health_status == 200
        assert health["status"] == "ready"
        assert validate_status == 200
        assert validation["diagnostics"] == [], validation
        assert preview_status == 200
        assert preview["status"] == "completed"
    finally:
        host.stop()


def test_queryflux_execution_is_bound_to_an_existing_project_in_workspace(tmp_path) -> None:
    plugin = DataEnginerringStudioPlugin()
    workspaces_plugin = WorkspacesPlugin()
    transport = _QueryFluxTransport()
    provider = QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake(
                "queryflux",
                "qf-1",
                EngineCapabilities((("cancel", True),)),
                True,
            ),
            ("duckdb",),
            "ready",
        ),
        QueryExecutionPolicy((("queryflux", ("duckdb",)),), required_capability="cancel"),
    )
    services = {
        "artifact_store": LocalArtifactStore(tmp_path / "artifacts"),
        "queryflux_runtime_provider": provider,
        "queryflux_transport": transport,
        "queryflux_evidence_reference_store": SqliteQueryEvidenceReferenceStore(
            tmp_path / "evidence.db"
        ),
    }
    manager = PluginManager()
    plan = manager.compose(
        (
            PluginRecord(workspaces_plugin.manifest, workspaces_plugin, "test"),
            PluginRecord(plugin.manifest, plugin, "test"),
        ),
        services=services,
    )
    host = PluginHost(manager, plan)
    host.start()

    store = _Store()
    workspace_a = WorkspaceId("workspace-a")
    workspace_b = WorkspaceId("workspace-b")
    store.workspaces[workspace_a] = Workspace(workspace_a, "Workspace A")
    store.workspaces[workspace_b] = Workspace(workspace_b, "Workspace B")
    store.projects[(workspace_a, ProjectId("project-1"))] = _manifest()
    store.projects[(workspace_b, ProjectId("project-2"))] = _manifest(
        name="Project B", project_id=ProjectId("project-2")
    )
    authorizer = _Authorizer()
    request_body = {
        "sql": "SELECT 1",
        "profile": "queryflux",
        "engine": "duckdb",
        "run_id": "run-1",
        "attempt_id": "attempt-1",
    }
    try:
        with _server(
            store,
            authorizer,
            plugin_host=host,
            plugin_routes_enabled=True,
        ) as address:
            success_status, success = _request(
                address,
                "POST",
                "/v1/workspaces/workspace-a/projects/project-1/data-engineering/queryflux/execute",
                request_body,
            )
            cross_workspace_status, cross_workspace = _request(
                address,
                "POST",
                "/v1/workspaces/workspace-a/projects/project-2/data-engineering/queryflux/execute",
                request_body,
            )

        assert success_status == 200
        assert success["rows"] == [[1]]
        assert cross_workspace_status == 404
        assert cross_workspace["error"]["code"] == "project_not_found"
        assert transport.submitted == 1
        assert [item.resource_ref for item in authorizer.requirements] == [
            "project-1",
            "project-2",
        ]
    finally:
        host.stop()


def test_pipeline_save_route_persists_canonical_document_with_revision_fence() -> None:
    writer = _PipelineWriter()
    with _server(
        _Store(),
        _Authorizer(),
        data_engineering_reader=writer,
    ) as address:
        status, payload = _request(
            address,
            "PUT",
            "/v1/workspaces/workspace-a/projects/project-1/pipelines/main",
            {
                "pipeline": {"version": 1, "nodes": [], "edges": []},
                "expected_revision": 0,
            },
        )

    assert status == 200
    assert payload["revision"] == 1
    assert len(writer.calls) == 1
    source = writer.calls[0]["source"]
    assert source.pipeline_documents[0][0] == "main.json"
    assert json.loads(source.pipeline_documents[0][1]) == {
        "edges": [],
        "nodes": [],
        "version": 1,
    }
