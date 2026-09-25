from threading import Event

import pytest

from studio_server.composition import LocalServerComposition


class _Server:
    def __init__(self) -> None:
        self.started = Event()
        self.stopped = Event()
        self.server_address = ("127.0.0.1", 0)

    def serve_forever(self) -> None:
        self.started.set()
        self.stopped.wait()

    def shutdown(self) -> None:
        self.stopped.set()

    def server_close(self) -> None:
        pass


class _PluginHost:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


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


def test_local_server_composition_lifecycles_plugins_around_servers() -> None:
    jobs = _Server()
    control = _Server()
    plugin_host = _PluginHost()
    composition = LocalServerComposition(jobs, control, plugin_host=plugin_host)

    composition.start()
    assert plugin_host.started
    composition.stop()
    assert plugin_host.stopped
