from ronin_plugin_performance.resources import load_config_schema, load_ui_manifest


def test_packaged_resources_are_operational_and_coherent():
    ui = load_ui_manifest()
    config = load_config_schema()
    assert ui["product"] == "Performance Studio"
    assert "runtime-method-hotspots" in ui["charts"]
    assert config["$id"] == "ronin.performance/config-v1"
