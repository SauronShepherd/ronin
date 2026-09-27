"""Local-first debugger session service for Data Engineering Studio."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass

from .ide import IdeCell, IdeSession, execute_ide_session


@dataclass(frozen=True, slots=True)
class DebugSnapshot:
    session_id: str
    cells: tuple[dict[str, object], ...]
    paused_at: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "cells": list(self.cells),
            "paused_at": self.paused_at,
        }


def snapshot(session: IdeSession) -> DebugSnapshot:
    return DebugSnapshot(
        session.session_id,
        tuple(asdict(cell) for cell in session.cells),
        session.paused_at,
    )


class DebuggerService:
    """Bounded in-memory debugger service; persistence can be injected later."""

    def __init__(self) -> None:
        self._sessions: dict[str, IdeSession] = {}

    def create(self, session_id: str, cells: tuple[IdeCell, ...] = ()) -> DebugSnapshot:
        if not session_id.strip() or len(session_id) > 256:
            raise ValueError("session_id must be non-empty and bounded")
        if session_id in self._sessions:
            raise ValueError("debug session already exists")
        session = IdeSession(session_id, cells)
        self._sessions[session_id] = session
        return snapshot(session)

    def get(self, session_id: str) -> DebugSnapshot:
        try:
            return snapshot(self._sessions[session_id])
        except KeyError as exc:
            raise KeyError("debug session not found") from exc

    def breakpoint(self, session_id: str, cell_id: str) -> DebugSnapshot:
        session = self._require(session_id)
        updated = session.toggle_breakpoint(cell_id)
        self._sessions[session_id] = updated
        return snapshot(updated)

    def replay(
        self, session_id: str, execute: Callable[[str], object], start_cell: str | None = None
    ) -> DebugSnapshot:
        updated = execute_ide_session(self._require(session_id), execute, start_cell=start_cell)
        self._sessions[session_id] = updated
        return snapshot(updated)

    def _require(self, session_id: str) -> IdeSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError("debug session not found") from exc


__all__ = ("DebugSnapshot", "DebuggerService", "snapshot")
