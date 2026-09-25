from __future__ import annotations

import pytest

from studio_core.plugins import (
    PluginDependency,
    PluginLoadError,
    PluginManager,
    PluginManifest,
    PluginRecord,
)


class _Plugin:
    def __init__(self, plugin_id: str, *, critical: bool = False, fail: bool = False) -> None:
        self.manifest = PluginManifest(
            id=plugin_id,
            name=plugin_id,
            version="1.0.0",
            plugin_api="1.0",
            critical=critical,
        )
        self.fail = fail
        self.started = False
        self.stopped = False

    def register(self, _context) -> None:
        return None

    def startup(self) -> None:
        if self.fail:
            raise RuntimeError("startup failed")
        self.started = True

    def shutdown(self) -> None:
        self.stopped = True


def test_critical_startup_failure_rolls_back_previous_plugins() -> None:
    first = _Plugin("first")
    critical = _Plugin("critical", critical=True, fail=True)
    critical.manifest = PluginManifest(
        id="critical",
        name="critical",
        version="1.0.0",
        plugin_api="1.0",
        critical=True,
        dependencies=(PluginDependency("first"),),
    )
    manager = PluginManager()
    plan = manager.compose(
        (
            PluginRecord(first.manifest, first, "test"),
            PluginRecord(critical.manifest, critical, "test"),
        )
    )

    with pytest.raises(PluginLoadError, match="critical plugin failed"):
        manager.start(plan)

    assert first.started
    assert first.stopped
    assert not critical.started
