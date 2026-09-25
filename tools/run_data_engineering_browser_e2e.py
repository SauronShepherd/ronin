"""Run a local same-origin browser qualification server for Data Enginerring Studio."""

from __future__ import annotations

import signal
from pathlib import Path
from threading import Event
from typing import cast

from test_workspace_project_http_api import _ACTOR, _Authorizer, _Store  # type: ignore[import-not-found]

from studio_core.plugins import PluginManager, PluginRecord
from studio_data_engineering import DataEnginerringStudioPlugin
from studio_execution import ProjectService, WorkspaceService
from studio_plugin_workspaces import WorkspacesPlugin
from studio_runtime import PluginHost
from studio_security.contracts import Actor
from studio_server import WorkspaceProjectHTTPServer


class _DevelopmentAuthenticator:
    def authenticate(self, _authorization: str | None) -> Actor | None:
        return cast(Actor, _ACTOR)


def main() -> None:
    store = _Store()
    manager = PluginManager()
    dependency = WorkspacesPlugin()
    plugin = DataEnginerringStudioPlugin()
    plan = manager.compose(
        (
            PluginRecord(dependency.manifest, dependency, "browser-e2e"),
            PluginRecord(plugin.manifest, plugin, "browser-e2e"),
        )
    )
    host = PluginHost(manager, plan)
    host.start()
    server = WorkspaceProjectHTTPServer(
        ("127.0.0.1", 8766),
        WorkspaceService(store),
        ProjectService(store),
        authenticator=_DevelopmentAuthenticator(),
        authorizer=_Authorizer(),
        plugin_host=host,
        plugin_routes_enabled=True,
        studio_root=Path(__file__).parents[1] / "web",
    )
    stop = Event()
    signal.signal(signal.SIGINT, lambda *_args: stop.set())
    signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    try:
        server.timeout = 0.25
        while not stop.is_set():
            server.handle_request()
    finally:
        server.server_close()
        host.stop()


if __name__ == "__main__":
    main()
