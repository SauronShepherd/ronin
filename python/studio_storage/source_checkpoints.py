"""Atomic source-checkpoint persistence for connector-to-sink pipelines."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredSourceCheckpoint:
    source_id: str
    value: str
    generation: int


class SourceCheckpointConflict(RuntimeError):
    """Raised when a checkpoint CAS observes a newer committed generation."""


class SqliteSourceCheckpointStore:
    """Transactional CAS store for the connector-to-sink commit boundary."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS source_checkpoints ("
            "source_id TEXT PRIMARY KEY, value TEXT NOT NULL, generation INTEGER NOT NULL)"
        )
        self._connection.commit()

    def get(self, source_id: str) -> StoredSourceCheckpoint | None:
        row = self._connection.execute(
            "SELECT value, generation FROM source_checkpoints WHERE source_id=?", (source_id,)
        ).fetchone()
        return None if row is None else StoredSourceCheckpoint(source_id, row[0], row[1])

    def compare_and_set(
        self,
        source_id: str,
        expected: StoredSourceCheckpoint | None,
        next_value: str,
    ) -> StoredSourceCheckpoint:
        if not source_id or not source_id.strip() or not next_value or not next_value.strip():
            raise ValueError("source checkpoint identity and value are required")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self.get(source_id)
            if current != expected:
                raise SourceCheckpointConflict(f"source checkpoint changed: {source_id}")
            generation = 1 if current is None else current.generation + 1
            self._connection.execute(
                "INSERT INTO source_checkpoints(source_id,value,generation) VALUES(?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET "
                "value=excluded.value,generation=excluded.generation",
                (source_id, next_value, generation),
            )
            self._connection.commit()
            return StoredSourceCheckpoint(source_id, next_value, generation)
        except Exception:
            self._connection.rollback()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SqliteSourceCheckpointStore:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


__all__ = ("SourceCheckpointConflict", "SqliteSourceCheckpointStore", "StoredSourceCheckpoint")
