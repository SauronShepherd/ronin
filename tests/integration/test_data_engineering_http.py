from __future__ import annotations

import json
from pathlib import Path

from studio_core.ir import Node, OperatorRef, Port
from studio_core.plugins import PluginManager, PluginRecord
from studio_data_engineering import DataEnginerringStudioPlugin
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost
from test_workspace_project_http_api import _Authorizer, _server, _Store


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
            asset_connection.request(
                "GET", "/studio/data-enginerring-studio.html?e2e=1"
            )
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
            assert "Data Enginerring Studio" in asset_body
            assert health_status == 200
        assert health["status"] == "ready"
        assert validate_status == 200
        assert validation["diagnostics"] == [], validation
        assert preview_status == 200
        assert preview["status"] == "completed"
    finally:
        host.stop()
