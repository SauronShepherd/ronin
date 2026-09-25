from importlib.resources import files

from ronin_plugin_performance.analyzer import analyze_run
from ronin_plugin_performance.plugin import PLUGIN_ID, PerformancePlugin

from studio_core.plugins import ContributionRegistry, PluginContext


def test_analyzer_detects_spill_skew_shuffle_and_small_files():
    result = analyze_run(
        {
            "run_id": "r1",
            "stages": [
                {
                    "id": 4,
                    "duration_ms": 5000,
                    "shuffle_read_bytes": 80_000_000,
                    "shuffle_write_bytes": 40_000_000,
                    "spill_disk_bytes": 10,
                    "tasks": [{"duration_ms": 100}, {"duration_ms": 1000}],
                }
            ],
            "assets": [{"id": "events", "bytes": 10_000_000, "file_count": 200}],
        }
    )
    assert {i["code"] for i in result["issues"]} == {
        "task-skew",
        "spill",
        "shuffle-pressure",
        "small-files",
    }
    assert result["series"]["stages"][0]["shuffle_bytes"] == 120_000_000


def test_analyzer_detects_gc_pressure_and_low_parallelism():
    result = analyze_run(
        {
            "stages": [
                {"id": 1, "duration_ms": 2000, "gc_time_ms": 600, "tasks": [{"duration_ms": 2000}]}
            ]
        }
    )
    assert {item["code"] for item in result["issues"]} == {"gc-pressure", "low-parallelism"}


def test_plugin_registers_worker_job_and_ui():
    plugin = PerformancePlugin()
    registry = ContributionRegistry()
    plugin.register(PluginContext(PLUGIN_ID, registry, {}))
    assert "performance.analysis" in registry.capabilities
    assert [j.job_type for j in registry.job_registry.items] == ["performance.analyze"]
    assert [(route.method, route.path) for route in registry.routes] == [
        ("POST", "/api/v1/performance/analyze")
    ]
    assert registry.ui_registry.items[0].manifest["charts"]
    assert files("ronin_plugin_performance").joinpath("ui_manifest.json").is_file()
    assert files("ronin_plugin_performance").joinpath("config_schema.json").is_file()
