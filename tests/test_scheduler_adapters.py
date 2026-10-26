from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from studio_connectors import IngestionSyncCancelled
from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_execution import (
    SchedulerWorkloadCancelled,
    UnsupportedSchedulerWorkload,
    execute_scheduler_job,
)
from studio_ml import PipelineIR, PipelineNode
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.services import InMemoryMLLabStore, LabService
from studio_orchestrator import Instant, Job, JobId, JobState
from studio_sql import SqlColumn, SqlQueryResult
from studio_storage import LocalArtifactStore


class Engine:
    def execute(self, sql: str, parameters: tuple[object, ...], *, max_rows: int) -> SqlQueryResult:
        del max_rows
        assert sql == "SELECT 1"
        assert parameters == ()
        return SqlQueryResult((SqlColumn("value", "INTEGER"),), ((1,),))


def _job(target: str, payload: object | None = None) -> Job:
    now = Instant("2026-09-24T00:00:00.000000Z")
    return Job(
        id=JobId("job-1"),
        project_id="project-1",
        idempotency_key="key-1",
        request_digest="a" * 64,
        state=JobState.QUEUED,
        created_at=now,
        updated_at=now,
        target=target,
        parameters_json=json.dumps(
            payload if payload is not None else {"query": "SELECT 1", "parameters": {}}
        ),
    )


def _ml_lab() -> Lab:
    return Lab(
        "lab-1",
        "Churn",
        "project-1",
        AssetRef(AssetId("dataset-1"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("age"),),
    )


def _compiled_ml_pipeline(lab: Lab) -> PipelineIR:
    service = LabService(InMemoryMLLabStore())
    service.create(WorkspaceId("workspace-1"), lab)
    return service.compile(WorkspaceId("workspace-1"), lab.id)


def test_scheduler_dispatch_routes_sql_without_notebook_fallback() -> None:
    result = execute_scheduler_job(_job("sql.query"), sql_engine=Engine())
    assert result.family == "sql"
    assert result.sql is not None
    assert result.sql.result.rows == ((1,),)
    assert result.evidence_payload()["evidence_digest"] == result.sql.evidence_digest
    assert result.evidence_payload()["rows"] == [[1]]


def test_scheduler_dispatch_rejects_unqualified_family() -> None:
    with pytest.raises(UnsupportedSchedulerWorkload, match="ml.run requires"):
        execute_scheduler_job(_job("ml.run"))


def test_connector_sync_scheduler_requires_and_forwards_workspace_scope() -> None:
    seen: dict[str, object] = {}
    connection = object()
    asset = object()
    secrets = object()

    class SyncService:
        def execute(self, definition, *, workspace_id, **kwargs):
            seen.update({"definition": definition, "workspace_id": workspace_id, **kwargs})
            return {"schema": "ronin.ingestion-sync-result/v1"}

    dependencies = {
        "connector_sync_service": SyncService(),
        "connector_connection": lambda workspace, reference: (
            seen.update({"resolved_workspace": workspace, "connection_ref": reference})
            or connection
        ),
        "connector_asset": lambda resolved_connection, reference: (
            seen.update({"asset_connection": resolved_connection, "asset_ref": reference}) or asset
        ),
        "connector_secrets": lambda reference: seen.update({"secrets_ref": reference}) or secrets,
        "connector_destination": object(),
    }
    with pytest.raises(UnsupportedSchedulerWorkload, match="workspace scope"):
        execute_scheduler_job(
            _job(
                "connector.sync.v1",
                {
                    "connector_id": "postgres",
                    "source_ref": "conn-1::public.orders",
                    "destination_ref": "artifact://orders",
                    "checkpoint_ref": "orders",
                },
            ),
            **dependencies,
        )

    result = execute_scheduler_job(
        _job(
            "connector.sync.v1",
            {
                "connector_id": "postgres",
                "source_ref": "conn-1::public.orders",
                "destination_ref": "artifact://orders",
                "checkpoint_ref": "orders",
            },
        ),
        workspace_id="workspace-a",
        **dependencies,
    )
    assert result.family == "connector"
    assert seen["workspace_id"] == "workspace-a"
    assert seen["definition"].checkpoint_identity == "orders"
    assert seen["definition"].connection_ref == "conn-1"
    assert seen["definition"].asset_ref == "public.orders"
    assert seen["resolved_workspace"] == "workspace-a"
    assert seen["connection_ref"] == "conn-1"
    assert seen["asset_connection"] is connection
    assert seen["asset_ref"] == "public.orders"
    assert seen["secrets_ref"] == "conn-1"
    assert seen["connection"] is connection
    assert seen["asset"] is asset
    assert seen["secrets"] is secrets


def test_connector_sync_scheduler_maps_cooperative_cancellation() -> None:
    class SyncService:
        def execute(self, *_args, cancellation_requested=None, **_kwargs):
            assert cancellation_requested is not None
            assert cancellation_requested()
            raise IngestionSyncCancelled("cancelled at sync safe point")

    with pytest.raises(SchedulerWorkloadCancelled, match="safe point"):
        execute_scheduler_job(
            _job(
                "connector.sync.v1",
                {
                    "connector_id": "postgres",
                    "source_ref": "conn-1::public.orders",
                    "destination_ref": "artifact://orders",
                    "checkpoint_ref": "orders",
                },
            ),
            connector_sync_service=SyncService(),
            connector_connection=object(),
            connector_asset=object(),
            connector_secrets=object(),
            connector_destination=object(),
            workspace_id="workspace-a",
            cancellation_requested=lambda: True,
        )


@pytest.mark.parametrize("identifier", ["", " ", "\t"])
def test_scheduler_dispatch_rejects_blank_ml_identifiers(identifier: str) -> None:
    class Runner:
        def run(self, _lab, _rows):
            return SimpleNamespace(to_payload=lambda: {})

    with pytest.raises(
        UnsupportedSchedulerWorkload,
        match="ML runner, lab, pipeline, and rows|parameters",
    ):
        execute_scheduler_job(
            _job("ml.run", {"lab_id": identifier, "dataset_ref": "dataset-1"}),
            ml_runner=Runner(),
            ml_lab=object(),
            ml_pipeline=PipelineIR((PipelineNode("train", "train"),)),
            ml_rows=(),
        )


def test_scheduler_dispatch_pins_ml_pipeline_and_records_its_digest() -> None:
    lab = _ml_lab()
    pipeline = _compiled_ml_pipeline(lab)
    seen: dict[str, object] = {}

    class Runner:
        def execute_pipeline(self, lab, rows, submitted_pipeline):
            seen.update({"lab": lab, "rows": rows, "pipeline": submitted_pipeline})
            return SimpleNamespace(to_payload=lambda: {"status": "completed"})

    rows = ({"value": 1},)
    result = execute_scheduler_job(
        _job(
            "ml.run",
            {
                "lab_id": "lab-1",
                "pipeline_digest": pipeline.digest,
                "dataset_ref": "dataset-1",
            },
        ),
        ml_runner=Runner(),
        ml_lab=lab,
        ml_pipeline=pipeline,
        ml_rows=rows,
    )

    assert seen == {"lab": lab, "rows": rows, "pipeline": pipeline}
    assert result.family == "ml"
    assert result.evidence_payload()["ml"]["pipeline_digest"] == pipeline.digest


def test_scheduler_dispatch_passes_custom_pinned_pipeline_to_runner() -> None:
    lab = _ml_lab()
    canonical = _compiled_ml_pipeline(lab)
    pipeline = PipelineIR(
        canonical.nodes,
        parameters=tuple(
            (key, "custom-seed" if key == "seed" else value) for key, value in canonical.parameters
        ),
    )
    seen: dict[str, object] = {}

    class Runner:
        def execute_pipeline(self, submitted_lab, rows, submitted_pipeline):
            seen.update({"lab": submitted_lab, "rows": rows, "pipeline": submitted_pipeline})
            return SimpleNamespace(to_payload=lambda: {"status": "completed"})

    rows = ({"value": 1},)
    result = execute_scheduler_job(
        _job(
            "ml.run",
            {
                "lab_id": lab.id,
                "pipeline_digest": pipeline.digest,
                "dataset_ref": "dataset-1",
            },
        ),
        ml_runner=Runner(),
        ml_lab=lab,
        ml_pipeline=pipeline,
        ml_rows=rows,
    )

    assert seen == {"lab": lab, "rows": rows, "pipeline": pipeline}
    assert result.evidence_payload()["ml"]["pipeline_digest"] == pipeline.digest


def test_scheduler_dispatch_rejects_pipeline_for_legacy_runner() -> None:
    lab = _ml_lab()
    canonical = _compiled_ml_pipeline(lab)
    custom = PipelineIR(
        canonical.nodes,
        parameters=tuple(
            (key, "custom-seed" if key == "seed" else value) for key, value in canonical.parameters
        ),
    )

    class LegacyRunner:
        def run(self, *_args):
            raise AssertionError("custom pipeline must not fall back to Lab-only execution")

    with pytest.raises(UnsupportedSchedulerWorkload, match="cannot execute the planned pipeline"):
        execute_scheduler_job(
            _job(
                "ml.run",
                {
                    "lab_id": lab.id,
                    "pipeline_digest": custom.digest,
                    "dataset_ref": "dataset-1",
                },
            ),
            ml_runner=LegacyRunner(),
            ml_lab=lab,
            ml_pipeline=custom,
            ml_rows=(),
        )


def test_scheduler_dispatch_rejects_changed_ml_pipeline_before_running() -> None:
    lab = _ml_lab()
    planned = _compiled_ml_pipeline(lab)
    changed = PipelineIR(
        planned.nodes,
        parameters=tuple(
            (key, "99" if key == "seed" else value) for key, value in planned.parameters
        ),
    )
    called = False

    class Runner:
        def run(self, *_args):
            nonlocal called
            called = True
            return SimpleNamespace(to_payload=lambda: {})

    with pytest.raises(UnsupportedSchedulerWorkload, match="does not match the planned pipeline"):
        execute_scheduler_job(
            _job(
                "ml.run",
                {
                    "lab_id": "lab-1",
                    "pipeline_digest": planned.digest,
                    "dataset_ref": "dataset-1",
                },
            ),
            ml_runner=Runner(),
            ml_lab=lab,
            ml_pipeline=changed,
            ml_rows=(),
        )
    assert called is False


def test_scheduler_dispatch_rejects_pipeline_pinned_to_an_old_lab_definition() -> None:
    planned_lab = _ml_lab()
    current_lab = Lab(
        planned_lab.id,
        planned_lab.name,
        planned_lab.project_id,
        planned_lab.dataset,
        planned_lab.target,
        planned_lab.task,
        (FeatureSpec("income"),),
    )
    planned_pipeline = _compiled_ml_pipeline(planned_lab)
    called = False

    class Runner:
        def run(self, *_args):
            nonlocal called
            called = True
            return SimpleNamespace(to_payload=lambda: {})

    with pytest.raises(
        UnsupportedSchedulerWorkload,
        match="does not pin the current lab definition",
    ):
        execute_scheduler_job(
            _job(
                "ml.run",
                {
                    "lab_id": current_lab.id,
                    "pipeline_digest": planned_pipeline.digest,
                    "dataset_ref": "dataset-1",
                },
            ),
            ml_runner=Runner(),
            ml_lab=current_lab,
            ml_pipeline=planned_pipeline,
            ml_rows=(),
        )
    assert called is False


@pytest.mark.parametrize("destination_ref", ["", " ", "\t"])
def test_scheduler_dispatch_rejects_blank_notification_destination(destination_ref: str) -> None:
    payload = b'{"kind":"alert","title":"t","body":"b"}'

    with pytest.raises(UnsupportedSchedulerWorkload, match="destination is invalid"):
        execute_scheduler_job(
            _job(
                "notification.send",
                {
                    "notification_id": "notification-1",
                    "channel": "webhook",
                    "destination_ref": destination_ref,
                    "payload_ref": "artifact://sha256/" + "a" * 64,
                },
            ),
            notification_sink=SimpleNamespace(send=lambda _intent: "notification-1"),
            notification_artifacts=SimpleNamespace(
                get_bytes_by_storage_ref=lambda *_args, **_kwargs: payload
            ),
        )


def test_scheduler_dispatch_routes_semantic_refresh_through_injected_runner() -> None:
    class Runner:
        def run(
            self, *, model_id: str, definition_digest: str, tile_limit: int
        ) -> dict[str, object]:
            return {
                "model_id": model_id,
                "definition_digest": definition_digest,
                "tile_limit": tile_limit,
                "status": "refreshed",
            }

    result = execute_scheduler_job(
        _job(
            "semantic.refresh",
            {"model_id": "orders", "definition_digest": "b" * 64, "tile_limit": 25},
        ),
        semantic_refresh_runner=Runner(),
    )
    assert result.family == "semantic"
    assert result.evidence_payload()["semantic"]["status"] == "refreshed"


def test_scheduler_dispatch_routes_pipeline_run_through_injected_runner() -> None:
    class Runner:
        def run(
            self,
            *,
            revision_key: str,
            ir_digest: str,
            runtime: str,
            parameters: dict[str, object],
        ) -> dict[str, object]:
            return {
                "revision_key": revision_key,
                "ir_digest": ir_digest,
                "runtime": runtime,
                "parameters": parameters,
                "status": "succeeded",
            }

    result = execute_scheduler_job(
        _job(
            "data-engineering.pipeline-run.v1",
            {
                "revision_key": "orders-v1",
                "ir_digest": "c" * 64,
                "runtime": "local",
                "parameters": {"limit": 10},
            },
        ),
        pipeline_runner=Runner(),
    )
    assert result.family == "pipeline"
    assert result.evidence_payload()["pipeline"]["status"] == "succeeded"


def test_scheduler_dispatch_routes_graph_query() -> None:
    object_ref = SimpleNamespace(object_type="Order", key=(("id", 1),))
    graph_object = SimpleNamespace(ref=object_ref, properties=(("total", 5),))

    def query(_graph_id: str, _query: str, *, max_limit: int) -> SimpleNamespace:
        del max_limit
        return SimpleNamespace(objects=(graph_object,))

    adapter = SimpleNamespace(query=query)
    result = execute_scheduler_job(
        _job(
            "graph.query",
            {"graph_id": "orders", "query": "SELECT o FROM Order o", "limit": 10},
        ),
        graph_adapter=adapter,
    )
    assert result.family == "graph"
    assert result.evidence_payload()["objects"][0]["object_type"] == "Order"


@pytest.mark.parametrize("limit", [0, -1, 10_001, True, "10"])
def test_scheduler_dispatch_rejects_invalid_graph_query_limits(limit: object) -> None:
    adapter = SimpleNamespace(query=lambda *_args, **_kwargs: SimpleNamespace(objects=()))

    with pytest.raises(UnsupportedSchedulerWorkload, match="graph.query parameters are invalid"):
        execute_scheduler_job(
            _job(
                "graph.query",
                {"graph_id": "orders", "query": "SELECT o FROM Order o", "limit": limit},
            ),
            graph_adapter=adapter,
        )


def test_scheduler_dispatch_rejects_graph_adapter_result_over_limit() -> None:
    object_ref = SimpleNamespace(object_type="Order", key=(("id", 1),))
    graph_object = SimpleNamespace(ref=object_ref, properties=())
    adapter = SimpleNamespace(
        query=lambda *_args, **_kwargs: SimpleNamespace(objects=(graph_object, graph_object))
    )

    with pytest.raises(UnsupportedSchedulerWorkload, match="exceeded max_limit"):
        execute_scheduler_job(
            _job(
                "graph.query",
                {"graph_id": "orders", "query": "SELECT o FROM Order o", "limit": 1},
            ),
            graph_adapter=adapter,
        )


def test_scheduler_dispatch_routes_quality_gate_through_rows_artifact(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    rows_ref = store.put_bytes(role="quality-rows", data=b'[{"id": 1}]').storage_ref
    seen: dict[str, object] = {}

    class Quality:
        def run(self, workspace_id, payload, *, now):
            seen.update({"workspace": workspace_id, "payload": payload, "now": now})
            return {"run": {"status": "passed"}, "gate_passed": True}

    result = execute_scheduler_job(
        _job(
            "quality.gate",
            {
                "asset_id": "orders",
                "version": "v1",
                "contract_digest": "a" * 64,
                "rows_ref": rows_ref,
            },
        ),
        quality_adapter=Quality(),
        artifact_store=store,
        workspace_id="workspace-1",
        run_id="run-1",
    )
    assert result.family == "quality"
    assert seen["payload"]["rows"] == [{"id": 1}]
    assert seen["payload"]["contract_digest"] == "a" * 64
