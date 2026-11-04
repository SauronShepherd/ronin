from __future__ import annotations

# ruff: noqa: E501
import http.client
import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_core.ml import (
    ExperimentId,
    MetricValue,
    MLRunId,
    MLRunRecord,
    ModelEvaluation,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_core.plugins import PluginManager, PluginRecord
from studio_ml import FeatureDefinitionService
from studio_ml.orchestration import LocalExecutionCoordinator
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_ml.sqlite import SqliteMLLabStore
from studio_orchestrator import Instant
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost
from studio_storage.ml import MLConflict
from test_workspace_project_http_api import _Authorizer, _server, _Store


def _request(
    address: tuple[str, int], method: str, path: str, body: object
) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection(*address, timeout=10)
    payload = json.dumps(body).encode("utf-8") if method != "GET" else None
    headers = {"Authorization": "Bearer good"}
    if payload is not None:
        headers.update(
            {
                "Content-Type": "application/json",
                "Content-Length": str(len(payload)),
            }
        )
    connection.request(
        method,
        path,
        body=payload,
        headers=headers,
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

    class FakeRunner:
        def run(self, _lab, _rows):
            return SimpleNamespace(to_payload=lambda: {"runner": "fake"})

    ml._coordinator.close()
    ml._coordinator = LocalExecutionCoordinator(runner=FakeRunner())
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
            list_status, listed = _request(
                address,
                "GET",
                "/v1/ml-studio/labs?workspace_id=workspace-a",
                {},
            )
            assert list_status == 200, listed
            assert [item["id"] for item in listed["items"]] == ["http-lab"]
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
            retry_status, _retry = _request(
                address,
                "POST",
                "/v1/ml-studio/labs/http-lab/executions?workspace_id=workspace-a",
                {"run_id": "http-run", "rows": rows},
            )
            assert retry_status == 200
            conflict_status, conflict = _request(
                address,
                "POST",
                "/v1/ml-studio/labs/http-lab/executions?workspace_id=workspace-a",
                {"run_id": "http-run", "rows": rows[:-1]},
            )
            assert conflict_status == 409, conflict

            other_lab = {
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
            }
            other_status, _ = _request(
                address,
                "POST",
                "/v1/ml-studio/labs?workspace_id=workspace-b",
                other_lab,
            )
            assert other_status == 200
            for workspace in ("workspace-a", "workspace-b"):
                submitted_status, submitted = _request(
                    address,
                    "POST",
                    f"/v1/ml-studio/labs/http-lab/executions?workspace_id={workspace}",
                    {"run_id": "shared-run", "rows": rows},
                )
                assert submitted_status == 200, submitted
            for _ in range(300):
                snapshots = [
                    _request(
                        address,
                        "GET",
                        f"/v1/ml-studio/executions/shared-run?workspace_id={workspace}",
                        {},
                    )
                    for workspace in ("workspace-a", "workspace-b")
                ]
                if all(
                    status == 200 and item.get("state") == "succeeded" for status, item in snapshots
                ):
                    break
                time.sleep(0.01)
            assert all(status == 200 for status, _item in snapshots)
            assert all(item["state"] == "succeeded" for _status, item in snapshots), snapshots
            unknown_status, unknown = _request(
                address,
                "GET",
                "/v1/ml-studio/executions/shared-run?workspace_id=workspace-c",
                {},
            )
            assert unknown_status == 404, unknown
    finally:
        host.stop()


def test_ml_model_evaluation_review_gates_promotion_over_http() -> None:
    manager = PluginManager()
    workspaces = WorkspacesPlugin()
    ml = MachineLearningStudioPlugin()
    model = RegisteredModelVersion(
        ModelId("review-model"),
        ModelVersion("candidate-1"),
        MLRunId("review-run"),
        "artifact://review-model/candidate-1",
        "a" * 64,
        "scikit-learn",
        ModelSignature((("x", "number"),), (("target", "number"),)),
    )
    run = MLRunRecord(
        MLRunId("review-run"),
        ExperimentId("review-experiment"),
        "execution:review-run",
        "revision:review",
        (AssetRef(AssetId("customers"), AssetVersion("v1")),),
        metrics=(MetricValue("accuracy", 0.9),),
    )

    class Registry:
        def __init__(self) -> None:
            self.model = model
            self.evaluations: list[ModelEvaluation] = []

        def get_model(self, _workspace, model_id, version):
            return self.model if (model_id, version) == (model.model_id, model.version) else None

        def get_run(self, _workspace, run_id):
            return run if run_id == run.id else None

        def record_evaluation(self, _workspace, evaluation, *, now):
            assert now
            if evaluation not in self.evaluations:
                self.evaluations.append(evaluation)
            return evaluation

        def list_evaluations(self, _workspace, model_id, version):
            if (model_id, version) != (model.model_id, model.version):
                return ()
            return tuple(self.evaluations)

        def promote_model(self, _workspace, model_id, version, *, now):
            assert now
            if (model_id, version) != (self.model.model_id, self.model.version):
                raise KeyError(f"{model_id}@{version}")
            if not any(item.status == "passed" for item in self.evaluations):
                raise MLConflict("promotion requires a passed model evaluation")
            self.model = replace(self.model, stage="champion")
            return self.model

    registry = Registry()
    plan = manager.compose(
        (
            PluginRecord(workspaces.manifest, workspaces, "test"),
            PluginRecord(ml.manifest, ml, "test"),
        )
    )
    host = PluginHost(manager, plan)
    host.start()
    ml._registry = registry
    try:
        with _server(
            _Store(),
            _Authorizer(),
            plugin_host=host,
            plugin_routes_enabled=True,
            studio_root=Path(__file__).parents[2] / "web",
        ) as address:
            model_path = "/v1/ml-studio/models/review-model/candidate-1"
            workspace = "?workspace_id=workspace-a"
            status, blocked = _request(
                address,
                "POST",
                f"{model_path}/promote{workspace}",
                {"reason": "review is required"},
            )
            assert status == 409, blocked
            assert blocked["error"]["code"] == "conflict"
            assert "passed model evaluation" in blocked["error"]["message"]

            invalid_status, invalid = _request(
                address,
                "POST",
                f"{model_path}/evaluations{workspace}",
                {"status": "passed", "review_ref": "review-1", "metrics": []},
            )
            assert invalid_status == 400, invalid

            status, unknown = _request(
                address,
                "POST",
                f"{model_path}/evaluations{workspace}",
                {"status": "unknown", "review_ref": "manual-review-unknown"},
            )
            assert status == 200, unknown
            assert unknown["evaluation"]["metrics"] == [
                {"name": "accuracy", "value": 0.9, "step": 0}
            ]
            status, still_blocked = _request(
                address,
                "POST",
                f"{model_path}/promote{workspace}",
                {"reason": "unknown review does not permit promotion"},
            )
            assert status == 409, still_blocked

            status, passed = _request(
                address,
                "POST",
                f"{model_path}/evaluations{workspace}",
                {"status": "passed", "review_ref": "manual-review-passed"},
            )
            assert status == 200, passed
            status, card = _request(address, "GET", f"{model_path}/card{workspace}", {})
            assert status == 200, card
            assert {item["status"] for item in card["evaluations"]} == {"passed", "unknown"}
            assert card["evaluations"][0]["dataset"] == {
                "asset_id": "customers",
                "version": "v1",
            }

            status, promoted = _request(
                address,
                "POST",
                f"{model_path}/promote{workspace}",
                {"reason": "passed operator review"},
            )
            assert status == 200, promoted
            assert promoted["stage"] == "champion"
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
