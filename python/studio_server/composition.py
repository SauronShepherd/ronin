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
        self._closed = False

    @property
    def ready(self) -> bool:
        return self._threads is not None and all(thread.is_alive() for thread in self._threads)

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("local server composition is closed")
        if self._threads is not None:
            raise RuntimeError("local server composition is already started")
        servers = (self.job_server, self.control_plane_server)
        started: list[tuple[StoppableServer, Thread]] = []
        plugin_start_attempted = False
        try:
            if self.plugin_host is not None:
                plugin_start_attempted = True
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
            for server, thread in zip(servers, threads, strict=True):
                thread.start()
                started.append((server, thread))
            self._threads = threads
        except Exception as startup_error:
            cleanup_errors: list[Exception] = []

            def attempt_cleanup(operation: Callable[[], object]) -> None:
                try:
                    operation()
                except Exception as exc:
                    cleanup_errors.append(exc)

            for server, _thread in reversed(started):
                attempt_cleanup(server.shutdown)
            for _server, thread in reversed(started):
                try:
                    thread.join(timeout=10.0)
                except Exception as exc:
                    cleanup_errors.append(exc)
                if thread.is_alive():
                    cleanup_errors.append(
                        RuntimeError(f"server thread survived startup rollback: {thread.name}")
                    )
            if self.plugin_host is not None and plugin_start_attempted:
                attempt_cleanup(self.plugin_host.stop)
            for server in servers:
                attempt_cleanup(server.server_close)
            self._threads = None
            self._closed = True
            for cleanup_error in cleanup_errors:
                startup_error.add_note(f"startup rollback also failed: {cleanup_error}")
            raise

    def stop(self) -> None:
        if self._closed:
            return
        threads = self._threads
        failures: list[Exception] = []

        def attempt(operation: Callable[[], object]) -> None:
            try:
                operation()
            except Exception as exc:
                failures.append(exc)

        servers = (self.job_server, self.control_plane_server)
        if threads is not None:
            for server in servers:
                attempt(server.shutdown)
            for thread in threads:
                try:
                    thread.join(timeout=10.0)
                except Exception as exc:
                    failures.append(exc)
                if thread.is_alive():
                    failures.append(RuntimeError(f"server thread did not stop: {thread.name}"))

        # Plugins can own workers that still use the shared job store. Stop those
        # consumers after HTTP ingress is quiesced but before closing server stores.
        if self.plugin_host is not None:
            attempt(self.plugin_host.stop)
        for server in servers:
            attempt(server.server_close)
        self._threads = None
        self._closed = True
        if failures:
            raise failures[0]


__all__ = ("LocalServerComposition", "PluginLifecycle", "StoppableServer")
