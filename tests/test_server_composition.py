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
