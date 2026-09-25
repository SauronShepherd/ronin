from __future__ import annotations

from pathlib import Path

import pytest

from studio_core.plugins import PluginManager, PluginRecord
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost, PluginLock, PluginLockError


def _host() -> PluginHost:
    plugin = WorkspacesPlugin()
    manager = PluginManager()
    plan = manager.compose((PluginRecord(plugin.manifest, plugin, "wheel:test"),))
    return PluginHost(manager, plan)


def test_lock_is_canonical_and_matches_composition() -> None:
    host = _host()

    lock = host.create_lock()

    assert lock.dumps() == lock.dumps()
    assert lock.plugins[0].id == "com.sauronshepherd.ronin.workspaces"
    host.verify_lock(lock)


def test_lock_round_trip_and_snapshot_file(tmp_path: Path) -> None:
    lock = _host().create_lock()
    path = tmp_path / "plugin-lock.json"

    lock.write(str(path))

    assert PluginLock.read(str(path)) == lock


def test_lock_rejects_changed_source_or_version() -> None:
    host = _host()
    lock = host.create_lock()
    entry = lock.plugins[0]
    changed = PluginLock(
        lock.schema_version,
        lock.host_version,
        lock.plugin_api,
        (type(entry)(**{**entry.as_dict(), "source": "tampered"}),),
    )

    with pytest.raises(PluginLockError, match="does not match"):
        host.verify_lock(changed)
