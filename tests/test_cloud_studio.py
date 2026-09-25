import pytest

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
from studio_core.plugins import ContributionRegistry, PluginContext


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
    assert isinstance(HttpEmulatorBackend("test", "http://127.0.0.1:4566").apply(topology()), dict)


def test_terraform_provider_config_is_endpoint_based_and_secret_free() -> None:
    config = terraform_provider_config(create_backend("floci"))
    assert 'dynamodb = "http://127.0.0.1:4566"' in config
    assert "AWS_ACCESS_KEY_ID" not in config


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


def test_external_health_reports_unreachable_without_raising() -> None:
    result = create_backend("floci", "http://127.0.0.1:1").health()
    assert result["available"] is False
    assert "error" in result
