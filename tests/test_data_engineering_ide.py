import pytest
from studio_data_engineering import IdeCell, IdeSession, execute_ide_session


def test_ide_session_executes_cells_and_pauses_at_breakpoint() -> None:
    session = IdeSession(
        "session-1",
        (IdeCell("a", "1"), IdeCell("b", "2", breakpoint=True), IdeCell("c", "3")),
    )
    paused = execute_ide_session(session, lambda source: int(source) + 1)
    assert next(cell for cell in paused.cells if cell.cell_id == "a").state == "succeeded"
    assert paused.paused_at == "b"
    assert next(cell for cell in paused.cells if cell.cell_id == "c").state == "idle"


def test_ide_session_records_user_code_failure() -> None:
    session = IdeSession("session-1", (IdeCell("a", "broken"),))

    def fail(_source):
        raise ValueError("bad cell")

    failed = execute_ide_session(session, fail)
    assert failed.cells[0].state == "failed"
    assert failed.cells[0].error == "bad cell"
    assert failed.paused_at == "a"


def test_ide_session_rejects_empty_cell_identity() -> None:
    with pytest.raises(ValueError, match="cell_id"):
        IdeSession("s").upsert(IdeCell("", "x"))
