"""SQLite-backed persistence for OpenLineage transport receipts."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SqliteOpenLineageDedupStore:
    """Bounded, restart-safe publication digest store."""

    def __init__(self, path: str | Path, *, max_entries: int = 4096) -> None:
        if (
            not isinstance(max_entries, int)
            or isinstance(max_entries, bool)
            or not 1 <= max_entries <= 100_000
        ):
            raise ValueError("max_entries must be between 1 and 100000")
        self._path = str(path)
        self._max_entries = max_entries
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ronin_openlineage_published ("
                "event_digest TEXT PRIMARY KEY, published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def contains(self, event_digest: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM ronin_openlineage_published WHERE event_digest=?",
                (event_digest,),
            ).fetchone()
        return row is not None

    def mark_published(self, event_digest: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO ronin_openlineage_published(event_digest) VALUES (?)",
                (event_digest,),
            )
            connection.execute(
                "DELETE FROM ronin_openlineage_published WHERE event_digest IN ("
                "SELECT event_digest FROM ronin_openlineage_published "
                "ORDER BY published_at,event_digest "
                "LIMIT MAX(0,(SELECT COUNT(*) FROM ronin_openlineage_published)-?))",
                (self._max_entries,),
            )
