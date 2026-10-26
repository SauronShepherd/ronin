from threading import Event, Thread

import pytest
from studio_server.composition import LocalServerComposition


class _Server:
    def __init__(self) -> None:
        self.started = Event()
        self.stopped = Event()
        self.closed = False
        self.server_address = ("127.0.0.1", 0)

    def serve_forever(self) -> None:
        self.started.set()
        self.stopped.wait()

    def shutdown(self) -> None:
        self.stopped.set()

    def server_close(self) -> None:
        self.closed = True


class _PluginHost:
    def __init__(self, servers: tuple[_Server, _Server] | None = None) -> None:
        self.started = False
        self.stopped = False
        self.servers = servers

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        if self.servers is not None:
            assert all(not server.closed for server in self.servers)
        self.stopped = True


class _FailingThread(Thread):
    def start(self) -> None:
        raise RuntimeError("injected thread start failure")


def test_local_server_composition_starts_and_stops_both_surfaces() -> None:
    jobs = _Server()
    control = _Server()
    composition = LocalServerComposition(jobs, control)

    composition.start()
    assert jobs.started.wait(1)
    assert control.started.wait(1)
    assert composition.ready
    with pytest.raises(RuntimeError):
        composition.start()

    composition.stop()
    assert not composition.ready
    with pytest.raises(RuntimeError, match="composition is closed"):
        composition.start()


def test_local_server_composition_lifecycles_plugins_around_servers() -> None:
    jobs = _Server()
    control = _Server()
    plugin_host = _PluginHost((jobs, control))
    composition = LocalServerComposition(jobs, control, plugin_host=plugin_host)

    composition.start()
    assert plugin_host.started
    composition.stop()
    assert plugin_host.stopped
    assert jobs.closed
    assert control.closed


def test_local_server_composition_rolls_back_partial_startup() -> None:
    jobs = _Server()
    control = _Server()
    plugin_host = _PluginHost((jobs, control))
    started_threads: list[Thread] = []

    def thread_factory(**kwargs) -> Thread:
        if kwargs["name"] == "ronin-control-plane":
            return _FailingThread(**kwargs)
        thread = Thread(**kwargs)
        started_threads.append(thread)
        return thread

    composition = LocalServerComposition(
        jobs, control, thread_factory=thread_factory, plugin_host=plugin_host
    )
    with pytest.raises(RuntimeError, match="injected thread start failure"):
        composition.start()

    assert jobs.started.wait(1)
    assert started_threads
    assert not started_threads[0].is_alive()
    assert plugin_host.stopped
    assert jobs.closed
    assert control.closed
    assert not composition.ready
    with pytest.raises(RuntimeError, match="composition is closed"):
        composition.start()
