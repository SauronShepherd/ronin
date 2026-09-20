from __future__ import annotations

# ruff: noqa: E501
import http.client
import json
from pathlib import Path

from studio_core.plugins import PluginManager, PluginRecord
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost
from test_workspace_project_http_api import _Authorizer, _server, _Store


def _request(address: tuple[str, int], method: str, path: str, body: object) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection(*address, timeout=10)
    payload = json.dumps(body).encode("utf-8")
    connection.request(method, path, body=payload, headers={
        "Authorization": "Bearer good", "Content-Type": "application/json",
        "Content-Length": str(len(payload)),
    })
    response = connection.getresponse()
    value = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, value


def test_ml_studio_http_lab_quality_and_execution_flow() -> None:
    manager = PluginManager()
    workspaces = WorkspacesPlugin()
    ml = MachineLearningStudioPlugin()
    plan = manager.compose(
        (PluginRecord(workspaces.manifest, workspaces, "test"), PluginRecord(ml.manifest, ml, "test"))
    )
    host = PluginHost(manager, plan)
    host.start()
    try:
        with _server(
            _Store(), _Authorizer(), plugin_host=host, plugin_routes_enabled=True,
            studio_root=Path(__file__).parents[2] / "web",
        ) as address:
            status, created = _request(address, "POST", "/v1/ml-studio/labs?workspace_id=workspace-a", {
                "schema": "ronin.ml-lab/v1", "id": "http-lab", "name": "HTTP Lab",
                "project_id": "project-1", "dataset": {"asset_id": "customers", "version": "v1"},
                "target": "target", "task": "classification", "features": [{"column": "x", "role": "numeric"}],
                "backend_id": "local.sklearn", "seed": 7, "test_fraction": 0.25,
            })
            assert status == 200, created
            rows = [{"x": n, "target": n % 2} for n in range(1, 21)]
            quality_status, quality = _request(
                address, "POST", "/v1/ml-studio/labs/http-lab/quality?workspace_id=workspace-a", {"rows": rows}
            )
            assert quality_status == 200
            assert quality["passed"] is True
            run_status, run = _request(
                address, "POST", "/v1/ml-studio/labs/http-lab/executions?workspace_id=workspace-a",
                {"run_id": "http-run", "rows": rows},
            )
            assert run_status == 200, run
            assert run["run_id"] == "http-run"
    finally:
        host.stop()
