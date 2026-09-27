from __future__ import annotations

import pytest

from studio_data_engineering.debugger import DebuggerService
from studio_data_engineering.ide import IdeCell


def test_debugger_creates_breakpoints_and_replays_until_failure() -> None:
    service = DebuggerService()
    service.create("session-1", (IdeCell("a", "1"), IdeCell("b", "fail")))
    service.breakpoint("session-1", "b")

    def execute(source: str) -> object:
        if source == "fail":
            raise RuntimeError("boom")
        return 1

    result = service.replay("session-1", execute)
    assert result.paused_at == "b"
    cells = {str(cell["cell_id"]): cell for cell in result.cells}
    assert cells["a"]["state"] == "succeeded"
    assert cells["b"]["state"] == "idle"


def test_debugger_rejects_duplicate_and_unknown_sessions() -> None:
    service = DebuggerService()
    service.create("session-1")
    with pytest.raises(ValueError, match="already exists"):
        service.create("session-1")
    with pytest.raises(KeyError, match="not found"):
        service.get("missing")
