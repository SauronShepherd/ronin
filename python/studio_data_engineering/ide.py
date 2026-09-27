"""Small, deterministic IDE session model for cell-by-cell pipeline debugging."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal

CellState = Literal["idle", "running", "succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class IdeCell:
    cell_id: str
    source: str
    state: CellState = "idle"
    output: object | None = None
    error: str | None = None
    breakpoint: bool = False


@dataclass(frozen=True, slots=True)
class IdeSession:
    session_id: str
    cells: tuple[IdeCell, ...] = ()
    paused_at: str | None = None

    def upsert(self, cell: IdeCell) -> IdeSession:
        if not cell.cell_id.strip():
            raise ValueError("cell_id must be non-empty")
        remaining = tuple(item for item in self.cells if item.cell_id != cell.cell_id)
        return replace(self, cells=remaining + (cell,))

    def toggle_breakpoint(self, cell_id: str) -> IdeSession:
        return replace(
            self,
            cells=tuple(
                replace(cell, breakpoint=not cell.breakpoint) if cell.cell_id == cell_id else cell
                for cell in self.cells
            ),
        )


def execute_ide_session(
    session: IdeSession,
    execute: Callable[[str], object],
    *,
    start_cell: str | None = None,
) -> IdeSession:
    """Execute cells in order, pausing before a breakpoint after the start cell."""
    started = start_cell is None
    current = session
    for cell in session.cells:
        if not started:
            started = cell.cell_id == start_cell
        if not started:
            continue
        if cell.breakpoint and cell.cell_id != start_cell:
            return replace(current, paused_at=cell.cell_id)
        running = current.upsert(replace(cell, state="running", error=None))
        try:
            output = execute(cell.source)
        except Exception as exc:  # noqa: BLE001 - debugger records user-code failure
            return replace(
                running.upsert(replace(cell, state="failed", error=str(exc))),
                paused_at=cell.cell_id,
            )
        current = running.upsert(replace(cell, state="succeeded", output=output))
    return replace(current, paused_at=None)


__all__ = ("CellState", "IdeCell", "IdeSession", "execute_ide_session")
