from io import BytesIO
from pathlib import Path

import pytest
import studio_cloud.backends as cloud_backends
from studio_cloud import (
    CloudEmulator,
    CloudResource,
    CloudTopology,
    SnapshotStore,
    create_backend,
    export_terraform,
    import_terraform,
    terraform_provider_config,
)
from studio_cloud.backends import HttpEmulatorBackend, TerraformEmulatorBackend
from studio_cloud.plugin import CloudStudioPlugin, factory
from studio_core.plugins import ContributionRegistry, PluginContext, PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost


def topology() -> CloudTopology:
    return CloudTopology(
        (CloudResource("bucket", "aws.s3.bucket", "assets", {"force_destroy": True}),)
    )


def test_topology_validates_and_exports_hcl() -> None:
    assert topology().validate() == []
    assert 'resource "aws_s3_bucket" "assets"' in export_terraform(topology())
    imported = import_terraform(export_terraform(topology()))
    assert imported.resources[0].name == "assets"


def test_hcl_import_rejects_expressions() -> None:
    with pytest.raises(ValueError, match="expressions"):
        import_terraform('resource "aws_s3_bucket" "x" { bucket = var.name }')


def test_emulator_applies_and_snapshots_state() -> None:
    emulator = CloudEmulator()
    assert emulator.apply(topology())["resources"][0]["name"] == "assets"
    assert emulator.plan(topology())["update"] == ["bucket"]
    assert emulator.destroy()["destroyed"] == ["bucket"]


def test_emulator_preserves_topology_edges_across_snapshot_round_trip() -> None:
    source = CloudTopology(
        (
            CloudResource("bucket", "aws.s3.bucket", "assets"),
            CloudResource("queue", "aws.sqs.queue", "events"),
        ),
        (("bucket", "queue"),),
    )
    snapshot = CloudEmulator().apply(source)
    assert snapshot["edges"] == [["bucket", "queue"]]
    assert CloudEmulator().import_snapshot(snapshot) == snapshot


def test_unknown_resource_is_rejected() -> None:
    assert CloudTopology((CloudResource("x", "azure.unknown", "x"),)).validate()


def test_resource_property_schema_rejects_non_scalar_types() -> None:
    errors = CloudTopology(
        (CloudResource("x", "aws.s3.bucket", "x", {"force_destroy": "yes"}),)
    ).validate()
    assert "must be boolean" in errors[0]


def test_external_backends_share_the_same_contract() -> None:
    floci = create_backend("floci")
    localstack = create_backend("localstack")
    assert floci.health()["endpoint"] == "http://127.0.0.1:4566"
    assert localstack.health()["license_required"] is True
    assert isinstance(floci, TerraformEmulatorBackend)
    assert isinstance(HttpEmulatorBackend("test", "http://127.0.0.1:4566"), HttpEmulatorBackend)


def test_http_backend_posts_real_json_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"accepted"}'

    captured: list[object] = []

    def fake_urlopen(request: object, timeout: float) -> Response:
        captured.append((request, timeout))
        return Response()

    monkeypatch.setattr(cloud_backends, "urlopen", fake_urlopen)
    result = HttpEmulatorBackend(
        "remote", "http://backend:4566", timeout_seconds=7
    ).apply(topology())
    request, timeout = captured[0]
    assert result == {"status": "accepted"}
    assert request.full_url == "http://backend:4566/v1/cloud-studio/apply"
    assert request.method == "POST"
    assert timeout == 7
    assert b'"aws.s3.bucket"' in request.data


def test_http_backend_exposes_rfc9457_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.error import HTTPError

    def failing_urlopen(_request: object, **_kwargs: object) -> object:
        raise HTTPError(
            "http://backend/v1/cloud-studio/refresh",
            422,
            "invalid topology",
            {"Content-Type": "application/problem+json"},
            BytesIO(b'{"type":"urn:ronin:invalid","title":"Invalid topology","detail":"bad edge"}'),
        )

    monkeypatch.setattr(cloud_backends, "urlopen", failing_urlopen)
    with pytest.raises(cloud_backends.HttpBackendError) as error:
        HttpEmulatorBackend("remote", "http://backend").refresh()
    assert error.value.status_code == 422
    assert error.value.problem["type"] == "urn:ronin:invalid"


def test_terraform_provider_config_is_endpoint_based_and_secret_free() -> None:
    config = terraform_provider_config(create_backend("floci"))
    assert "dynamodb = var.endpoint" in config
    assert "AWS_ACCESS_KEY_ID" not in config


def test_terraform_backend_writes_exact_pinned_tool_versions(tmp_path) -> None:
    backend = create_backend("floci", workspace_dir=str(tmp_path))

    backend._write_config(topology())

    config = (tmp_path / "main.tf").read_text(encoding="utf-8")
    provider = (tmp_path / "provider.tf").read_text(encoding="utf-8")
    variables = (tmp_path / "variables.tf").read_text(encoding="utf-8")
    resources = (tmp_path / "resources.tf").read_text(encoding="utf-8")
    lock = (tmp_path / ".terraform.lock.hcl").read_text(encoding="utf-8")
    assert 'required_version = "= 1.13.5"' in config
    assert 'version = "= 6.65.0"' in config
    assert "s3 = var.endpoint" in provider
    assert 'variable "endpoint"' in variables
    assert 'resource "aws_s3_bucket"' in resources
    assert 'version     = "6.65.0"' in lock
    assert 'constraints = "6.65.0"' in lock


def test_factory_reads_backend_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("RONIN_CLOUD_STUDIO_BACKEND", "floci")
    monkeypatch.setenv("RONIN_CLOUD_STUDIO_ENDPOINT", "http://emulator:4566")
    assert factory().backend.health()["endpoint"] == "http://emulator:4566"


def test_external_backend_workspace_is_injected(tmp_path) -> None:
    plugin = CloudStudioPlugin("floci", "http://127.0.0.1:4566", terraform_root=str(tmp_path))
    assert plugin.backend.workspace_dir == str(tmp_path)


def test_external_backend_accepts_plugin_cache_configuration(monkeypatch) -> None:
    monkeypatch.setenv("TF_PLUGIN_CACHE_DIR", "cache")
    backend = create_backend("floci")
    assert backend.plugin_cache_dir == "cache"


def test_opentofu_binary_is_configurable(monkeypatch) -> None:
    monkeypatch.setenv("RONIN_CLOUD_STUDIO_BACKEND", "floci")
    monkeypatch.setenv("RONIN_CLOUD_STUDIO_IAC", "tofu")
    assert factory().backend.terraform_executable == "tofu"


def test_plugin_api_lifecycle_is_operational() -> None:
    plugin = CloudStudioPlugin()
    payload = {
        "resources": [{"id": "bucket", "type": "aws.s3.bucket", "name": "assets"}],
        "edges": [],
    }
    assert plugin.validate(payload)["valid"] is True
    assert plugin.plan(payload)["create"] == ["bucket"]
    assert plugin.apply(payload)["resources"]
    assert plugin.refresh()["resources"]
    assert plugin.destroy()["destroyed"] == ["bucket"]


def test_cloud_api_route_passes_http_body_to_plugin_handler() -> None:
    plugin = CloudStudioPlugin()
    workspaces = WorkspacesPlugin()
    manager = PluginManager()
    host = PluginHost(
        manager,
        manager.compose(
            (
                PluginRecord(workspaces.manifest, workspaces, "test"),
                PluginRecord(plugin.manifest, plugin, "test"),
            )
        ),
    )
    host.start()
    try:
        response = host.invoke_route(
            "POST",
            "/v1/cloud-studio/validate",
            body={"resources": [], "edges": []},
        )
        assert response == {"valid": True, "errors": []}
    finally:
        host.stop()


def test_plugin_registers_complete_api_surface() -> None:
    plugin = CloudStudioPlugin()
    registry = ContributionRegistry()
    for capability in plugin.manifest.capabilities:
        registry.add_capability(capability, plugin.manifest.id)
    for permission in plugin.manifest.permissions:
        registry.add_permission(permission, plugin.manifest.id)
    plugin.register(PluginContext(plugin.manifest.id, registry, {}))
    paths = {route.path for route in registry.router_registry.items}
    assert {
        "/v1/cloud-studio/plan",
        "/v1/cloud-studio/apply",
        "/v1/cloud-studio/refresh",
        "/v1/cloud-studio/destroy",
    } <= paths
    assert "/v1/cloud-studio/import" in paths
    assert registry.ui_registry.items[0].manifest["entry"] == "cloud-studio.html"


def test_snapshot_can_be_imported() -> None:
    emulator = CloudEmulator()
    snapshot = emulator.apply(topology())
    restored = CloudEmulator().import_snapshot(snapshot)
    assert restored == snapshot


def test_snapshot_import_revalidates_resource_contract() -> None:
    emulator = CloudEmulator()
    with pytest.raises(ValueError, match="invalid snapshot"):
        emulator.import_snapshot(
            {
                "resources": [
                    {
                        "id": "bucket",
                        "type": "aws.s3.bucket",
                        "name": "bucket",
                        "properties": {"tags": {"secret": "nested"}},
                    }
                ]
            }
        )

    with pytest.raises(ValueError, match="missing id"):
        emulator.import_snapshot({"resources": [{"type": "aws.s3.bucket"}]})


def test_topology_rejects_unbounded_resource_shapes() -> None:
    too_many = CloudTopology(
        tuple(
            CloudResource("bucket-" + str(index), "aws.s3.bucket", "bucket") for index in range(257)
        )
    )
    assert any("resource limit" in error for error in too_many.validate())

    too_many_properties = CloudTopology(
        (
            CloudResource(
                "bucket",
                "aws.s3.bucket",
                "bucket",
                {f"property_{index}": "value" for index in range(65)},
            ),
        )
    )
    assert any("properties exceed limit" in error for error in too_many_properties.validate())


def test_plugin_snapshot_route_validates_and_normalizes_topology(tmp_path) -> None:
    plugin = CloudStudioPlugin(snapshot_dir=str(tmp_path))
    result = plugin.save_snapshot(
        {
            "workspace": "demo",
            "resources": [
                {
                    "id": "bucket",
                    "type": "aws.s3.bucket",
                    "name": "assets",
                    "properties": {"force_destroy": True},
                }
            ],
            "edges": [],
        }
    )
    assert result["snapshot"]["resources"][0]["properties"] == {"force_destroy": True}
    with pytest.raises(ValueError, match="invalid snapshot"):
        plugin.save_snapshot(
            {
                "workspace": "demo",
                "resources": [{"id": "bad", "type": "unknown", "name": "bad"}],
            }
        )


def test_plugin_isolates_in_memory_state_by_workspace() -> None:
    plugin = CloudStudioPlugin()
    payload = {
        "resources": [{"id": "bucket", "type": "aws.s3.bucket", "name": "assets"}],
    }
    assert plugin.apply({**payload, "workspace": "alpha"})["resources"]
    assert plugin.refresh(workspace="beta")["resources"] == []
    assert plugin.refresh(workspace="alpha")["resources"]
    plugin.destroy(workspace="alpha")
    assert plugin.refresh(workspace="alpha")["resources"] == []
    assert plugin.refresh(workspace="beta")["resources"] == []


def test_plugin_derives_isolated_terraform_workspace_directories(tmp_path) -> None:
    plugin = CloudStudioPlugin(
        backend_kind="floci",
        endpoint="http://127.0.0.1:4566",
        snapshot_dir=str(tmp_path / "snapshots"),
        terraform_root=str(tmp_path / "terraform"),
    )
    alpha = plugin._backend_for_workspace("alpha")
    beta = plugin._backend_for_workspace("beta")
    assert isinstance(alpha, TerraformEmulatorBackend)
    assert isinstance(beta, TerraformEmulatorBackend)
    assert alpha.workspace_dir != beta.workspace_dir
    assert alpha.workspace_dir.endswith("alpha")
    assert beta.workspace_dir.endswith("beta")
    assert Path(alpha.workspace_dir).is_dir()
    assert Path(beta.workspace_dir).is_dir()
    with pytest.raises(ValueError, match="unsafe"):
        plugin._backend_for_workspace("../escape")


def test_snapshot_store_round_trips_workspace(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    snapshot = {"resources": [{"id": "bucket"}], "edges": []}
    assert store.save("demo", snapshot) == snapshot
    assert store.load("demo") == snapshot
    assert store.load("missing") is None
    try:
        store.load("../escape")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe workspace must be rejected")


def test_snapshot_store_replaces_only_after_writing_complete_json(tmp_path) -> None:
    store = SnapshotStore(tmp_path)
    expected = {"resources": [{"id": "bucket"}], "edges": []}
    assert store.save("durable", expected) == expected
    assert (tmp_path / "durable.json").read_text(encoding="utf-8") == (
        '{"edges": [], "resources": [{"id": "bucket"}]}'
    )
    assert not (tmp_path / "durable.tmp").exists()


def test_snapshot_store_cleans_temporary_file_when_fsync_fails(tmp_path, monkeypatch) -> None:
    store = SnapshotStore(tmp_path)

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr("studio_cloud.engine.os.fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated disk failure"):
        store.save("failed", {"resources": [], "edges": []})
    assert not (tmp_path / "failed.json").exists()
    assert not (tmp_path / "failed.tmp").exists()


def test_external_health_reports_unreachable_without_raising() -> None:
    result = create_backend("floci", "http://127.0.0.1:1").health()
    assert result["available"] is False
    assert "error" in result


def test_external_health_requires_success_readiness_status() -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(503)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = create_backend("floci", f"http://127.0.0.1:{server.server_port}").health()
        assert result["available"] is False
        assert result["status_code"] == 503
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
