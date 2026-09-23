import pytest
from studio_core.operators import builtin_operator_catalog
from studio_core.plugins import ContributionRegistry, PluginContext
from studio_data_engineering import (
    DataEnginerringStudioPlugin,
    SqliteCompilationStore,
    compile_pipeline,
    preview_pipeline,
)
from studio_storage import LocalArtifactStore


def test_data_enginerring_studio_manifest_and_contributions(tmp_path) -> None:
    plugin = DataEnginerringStudioPlugin()
    plugin.manifest.validate()
    registry = ContributionRegistry()
    for capability in plugin.manifest.capabilities:
        registry.add_capability(capability, plugin.manifest.id)
    for permission in plugin.manifest.permissions:
        registry.add_permission(permission, plugin.manifest.id)

    plugin.register(
        PluginContext(
            plugin.manifest.id,
            registry,
            {"artifact_store": LocalArtifactStore(tmp_path / "artifacts")},
        )
    )
    registry.validate_manifest(plugin.manifest)

    assert plugin.manifest.name == "Data Enginerring Studio"
    assert "data-engineering.ir.v1" in registry.capabilities
    assert len(registry.routes) == 11
    assert registry.job_registry.items[0].job_type == "data-engineering.pipeline-run.v1"
    assert registry.ui_registry.items[0].manifest["navigation"][0]["label"] == (
        "Data Enginerring Studio"
    )
    assert registry.ui_registry.items[0].manifest["entry"] == (
        "/studio/data-enginerring-studio.html"
    )


def test_data_enginerring_studio_requires_startup_for_execution() -> None:
    plugin = DataEnginerringStudioPlugin()
    with pytest.raises(RuntimeError, match="not ready"):
        plugin.list_runtimes()


def test_plugin_health_reports_readiness_and_external_providers() -> None:
    plugin = DataEnginerringStudioPlugin()
    assert plugin.health()["status"] == "starting"
    plugin.startup()
    health = plugin.health()
    assert health["status"] == "ready"
    assert health["runtimes"]["spark-connect"] == "external-provider"


def test_pipeline_compiler_reports_validity_and_runtime() -> None:
    pipeline = {
        "config": {"name": "orders"},
        "nodes": [],
        "edges": [],
    }
    report = compile_pipeline(pipeline, runtime="local-preview", catalog=builtin_operator_catalog())
    assert report.portable is True
    assert report.node_count == 0
    assert report.edge_count == 0


def test_validation_persists_report_and_outbox(tmp_path) -> None:
    plugin = DataEnginerringStudioPlugin()
    registry = ContributionRegistry()
    for capability in plugin.manifest.capabilities:
        registry.add_capability(capability, plugin.manifest.id)
    for permission in plugin.manifest.permissions:
        registry.add_permission(permission, plugin.manifest.id)
    store = SqliteCompilationStore(tmp_path / "ronin.db")
    plugin.register(PluginContext(plugin.manifest.id, registry, {"compilation_store": store}))
    plugin.startup()
    result = plugin.validate_pipeline(
        body={
            "revision_key": "p/main/1",
            "runtime": "local-preview",
            "pipeline": {"config": {"name": "main"}, "nodes": [], "edges": []},
        }
    )
    assert result["portable"] is True
    assert (
        store.get_report(
            revision_key="p/main/1",
            runtime="local-preview",
            ir_digest=result["ir_digest"],
        )
        is not None
    )
    assert len(store.pending_events()) == 1
    assert plugin.get_compilation("p/main/1", "local-preview")["portable"] is True
    assert len(plugin.pending_events()["items"]) == 1


def test_pipeline_compiler_rejects_unknown_runtime() -> None:
    report = compile_pipeline(
        {"config": {"name": "orders"}, "nodes": [], "edges": []},
        runtime="unknown",
        catalog=builtin_operator_catalog(),
    )
    assert report.portable is False
    assert report.diagnostics[0].code == "RONIN-DE-001"


def test_preview_engine_runs_fixture_filter_select_and_derive() -> None:
    source = {
        "config": {"name": "orders"},
        "nodes": [
            {
                "id": "will-be-replaced",
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
    from studio_core.ir import Node, OperatorRef, Port

    node = Node.create(
        operator=OperatorRef("source.fixture"),
        instance_key="source",
        params={"fixture": "orders"},
        outputs=(Port("out"),),
    )
    source["nodes"][0]["id"] = node.id.value
    result = preview_pipeline(
        source,
        fixtures={"orders": [{"amount": 2}, {"amount": 7}]},
        row_limit=10,
    )
    assert result.rows_by_node["source"] == ({"amount": 2}, {"amount": 7})
    assert result.metrics["source"]["output_rows"] == 2


def test_plugin_preview_endpoint_returns_real_rows() -> None:
    plugin = DataEnginerringStudioPlugin()
    plugin.startup()
    from studio_core.ir import Node, OperatorRef, Port

    node = Node.create(
        operator=OperatorRef("source.fixture"),
        instance_key="source",
        params={"fixture": "orders"},
        outputs=(Port("out"),),
    )
    payload = {
        "pipeline": {
            "config": {"name": "orders"},
            "nodes": [
                {
                    "id": node.id.value,
                    "instance_key": node.instance_key,
                    "operator": {"name": node.operator.name, "version": 1},
                    "params": {"fixture": "orders"},
                    "inputs": [],
                    "outputs": [{"name": "out", "kind": "batch", "schema": None}],
                    "origin": {"view": "graph", "reference": None},
                    "ownership": "GRAPH",
                    "label": None,
                }
            ],
            "edges": [],
        },
        "fixtures": {"orders": [{"id": 1}]},
        "row_limit": 10,
    }
    result = plugin.preview_pipeline(body=payload)
    assert result["status"] == "completed"
    assert result["rows_by_node"] == {"source": [{"id": 1}]}


def test_plugin_sdp_import_route_persists_revision(tmp_path) -> None:
    plugin = DataEnginerringStudioPlugin()
    registry = ContributionRegistry()
    for capability in plugin.manifest.capabilities:
        registry.add_capability(capability, plugin.manifest.id)
    for permission in plugin.manifest.permissions:
        registry.add_permission(permission, plugin.manifest.id)
    plugin.register(
        PluginContext(
            plugin.manifest.id,
            registry,
            {"artifact_store": LocalArtifactStore(tmp_path / "artifacts")},
        )
    )
    plugin.startup()
    result = plugin.import_sdp(
        idempotency_key="import-1",
        body={
            "project_id": "retail",
            "pipeline_id": "main",
            "project_yaml": "name: retail\n",
            "pipeline_documents": [{"name": "pipelines/main.yaml", "content": "nodes: []\n"}],
        },
    )
    assert result["revision"] == 1
    assert result["source_digest"]


def test_submit_run_returns_durable_job_plan() -> None:
    plugin = DataEnginerringStudioPlugin()
    plugin.startup()
    result = plugin.submit_run(
        body={
            "project_id": "p",
            "revision_key": "main/1",
            "ir_digest": "c" * 64,
            "runtime": "local-preview",
        }
    )
    assert result["status"] == "planned"
    assert result["job_type"] == "data-engineering.pipeline-run.v1"
    assert result["job_id"]
    assert result["run_id"]


def test_pipeline_job_handler_executes_local_preview_and_fails_remote_closed() -> None:
    plugin = DataEnginerringStudioPlugin()
    plugin.startup()
    payload = {
        "runtime": "local-preview",
        "pipeline": {"config": {"name": "empty"}, "nodes": [], "edges": []},
    }
    result = plugin.run_pipeline(payload)
    assert result["status"] == "succeeded"
    assert result["runtime"] == "local-preview"
    failed = plugin.run_pipeline({**payload, "runtime": "spark-connect"})
    assert failed["status"] == "failed"
    assert failed["error_code"] == "DE-EXEC-006"
