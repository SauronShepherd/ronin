from __future__ import annotations

# ruff: noqa: E501
import http.client
import json
from pathlib import Path

from studio_core.plugins import PluginManager, PluginRecord
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml import FeatureDefinitionService
from studio_ml.sqlite import SqliteMLLabStore
from studio_orchestrator import Instant
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost
from test_workspace_project_http_api import _Authorizer, _server, _Store


def _request(
    address: tuple[str, int], method: str, path: str, body: object
) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection(*address, timeout=10)
    payload = json.dumps(body).encode("utf-8")
    connection.request(
        method,
        path,
        body=payload,
        headers={
            "Authorization": "Bearer good",
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        },
    )
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
        (
            PluginRecord(workspaces.manifest, workspaces, "test"),
            PluginRecord(ml.manifest, ml, "test"),
        )
    )
    host = PluginHost(manager, plan)
    host.start()
    try:
        with _server(
            _Store(),
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
            studio_root=Path(__file__).parents[2] / "web",
        ) as address:
            status, created = _request(
                address,
                "POST",
                "/v1/ml-studio/labs?workspace_id=workspace-a",
                {
                    "schema": "ronin.ml-lab/v1",
                    "id": "http-lab",
                    "name": "HTTP Lab",
                    "project_id": "project-1",
                    "dataset": {"asset_id": "customers", "version": "v1"},
                    "target": "target",
                    "task": "classification",
                    "features": [{"column": "x", "role": "numeric"}],
                    "backend_id": "local.sklearn",
                    "seed": 7,
                    "test_fraction": 0.25,
                },
            )
            assert status == 200, created
            rows = [{"x": n, "target": n % 2} for n in range(1, 21)]
            quality_status, quality = _request(
                address,
                "POST",
                "/v1/ml-studio/labs/http-lab/quality?workspace_id=workspace-a",
                {"rows": rows},
            )
            assert quality_status == 200
            assert quality["passed"] is True
            run_status, run = _request(
                address,
                "POST",
                "/v1/ml-studio/labs/http-lab/executions?workspace_id=workspace-a",
                {"run_id": "http-run", "rows": rows},
            )
            assert run_status == 200, run
            assert run["run_id"] == "http-run"
    finally:
        host.stop()


def test_ml_feature_definition_http_lifecycle_is_workspace_scoped(tmp_path: Path) -> None:
    store = SqliteMLLabStore(
        tmp_path / "ml.sqlite", migration_now=Instant("2026-09-23T00:00:00.000000Z")
    )
    with _server(
        _Store(),
        _Authorizer(),
        feature_definition_service=FeatureDefinitionService(store),
        studio_root=Path(__file__).parents[2] / "web",
    ) as address:
        definition = {
            "schema": "ronin.ml-feature/v1",
            "id": "features/customer",
            "name": "Customer features",
            "project_id": "project-1",
            "dataset": {"asset_id": "customers", "version": "v1"},
            "features": [{"column": "age", "role": "numeric"}],
            "transform": "identity",
            "version": 1,
        }
        status, created = _request(
            address, "POST", "/v1/ml-studio/features?workspace_id=workspace-a", definition
        )
        assert status == 201, created
        status, listed = _request(
            address, "GET", "/v1/ml-studio/features?workspace_id=workspace-a", {}
        )
        assert status == 200
        assert listed["items"][0]["id"] == "features/customer"
        status, fetched = _request(
            address,
            "GET",
            "/v1/ml-studio/features/features%2Fcustomer/1?workspace_id=workspace-a",
            {},
        )
        assert status == 200
        assert fetched["items"][0]["version"] == 1
        status, other = _request(
            address, "GET", "/v1/ml-studio/features?workspace_id=workspace-b", {}
        )
        assert status == 200
        assert other["items"] == []
