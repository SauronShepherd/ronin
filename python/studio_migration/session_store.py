"""SQLite persistence for Migration Studio session snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from studio_core.canonical_json import encode as encode_canonical_json

from .session import MigrationSession


class SQLiteMigrationSessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS migration_sessions ("
                "id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL, "
                "state TEXT NOT NULL, snapshot BLOB NOT NULL)"
            )

    def save(self, session: MigrationSession) -> None:
        payload = json.dumps(session.to_snapshot(), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO migration_sessions(id, workspace_id, project_id, state, snapshot) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "workspace_id=excluded.workspace_id, project_id=excluded.project_id, "
                "state=excluded.state, snapshot=excluded.snapshot",
                (
                    session.id,
                    session.workspace_id,
                    session.project_id,
                    session.state,
                    encode_canonical_json(json.loads(payload)),
                ),
            )

    def get(self, session_id: str, *, workspace_id: str, project_id: str) -> dict[str, object]:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT workspace_id, project_id, snapshot FROM migration_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"migration session not found: {session_id}")
        if row[0] != workspace_id or row[1] != project_id:
            raise PermissionError("migration session is outside the requested project scope")
        payload = json.loads(bytes(row[2]).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("stored migration session snapshot is invalid")
        return payload

    def load(self, session_id: str) -> MigrationSession:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT snapshot FROM migration_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"migration session not found: {session_id}")
        payload = json.loads(bytes(row[0]).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("stored migration session snapshot is invalid")
        return MigrationSession.from_snapshot(payload)

    def list(self, *, workspace_id: str, project_id: str) -> tuple[dict[str, object], ...]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT snapshot FROM migration_sessions WHERE workspace_id = ? AND project_id = ? "
                "ORDER BY id",
                (workspace_id, project_id),
            ).fetchall()
        return tuple(json.loads(bytes(row[0]).decode("utf-8")) for row in rows)


__all__ = ("SQLiteMigrationSessionStore",)
