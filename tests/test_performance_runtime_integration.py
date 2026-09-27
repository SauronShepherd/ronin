from ronin_plugin_performance.plugin import PerformancePlugin

from studio_core.plugins import PluginManager, PluginRecord
from studio_runtime import PluginHost


def test_plugin_host_invokes_performance_http_route():
    plugin = PerformancePlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "test"),))
    host = PluginHost(manager, plan)
    result = host.invoke_route(
        "POST", "/api/v1/performance/analyze", body={"run_id": "host", "stages": []}
    )
    assert result["run_id"] == "host"
