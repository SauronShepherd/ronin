"""Lifecycle coordination for the two local Ronin HTTP surfaces."""

from __future__ import annotations

from collections.abc import Callable
from threading import Thread
from typing import Protocol


class StoppableServer(Protocol):
    def serve_forever(self) -> None: ...

    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...


class PluginLifecycle(Protocol):
    def start(self) -> object: ...

    def stop(self) -> None: ...


class LocalServerComposition:
    """Start and stop job and control-plane servers as one local unit."""

    def __init__(
        self,
        job_server: StoppableServer,
        control_plane_server: StoppableServer,
        *,
        thread_factory: Callable[..., Thread] = Thread,
        plugin_host: PluginLifecycle | None = None,
    ) -> None:
        self.job_server = job_server
        self.control_plane_server = control_plane_server
        self._thread_factory = thread_factory
        self.plugin_host = plugin_host
        self._threads: tuple[Thread, Thread] | None = None

    @property
    def ready(self) -> bool:
        return self._threads is not None and all(thread.is_alive() for thread in self._threads)

    def start(self) -> None:
        if self._threads is not None:
            raise RuntimeError("local server composition is already started")
        if self.plugin_host is not None:
            self.plugin_host.start()
        threads = (
            self._thread_factory(
                target=self.job_server.serve_forever, name="ronin-jobs", daemon=True
            ),
            self._thread_factory(
                target=self.control_plane_server.serve_forever,
                name="ronin-control-plane",
                daemon=True,
            ),
        )
        for thread in threads:
            thread.start()
        self._threads = threads

    def stop(self) -> None:
        threads = self._threads
        if threads is None:
            return
        try:
            self.job_server.shutdown()
            self.control_plane_server.shutdown()
            for thread in threads:
                thread.join(timeout=10.0)
            self.job_server.server_close()
            self.control_plane_server.server_close()
        finally:
            if self.plugin_host is not None:
                self.plugin_host.stop()
            self._threads = None


__all__ = ("LocalServerComposition", "PluginLifecycle", "StoppableServer")
