"""Durable SQLite compare-and-set checkpoint store for streaming runtimes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import StreamCheckpoint, StreamPosition


class SqliteStreamCheckpointStore:
    """Reference durable checkpoint store with optimistic CAS semantics."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS stream_checkpoints ("
                "stream_id TEXT PRIMARY KEY, checkpoint_json TEXT NOT NULL, "
                "checkpoint_digest TEXT NOT NULL, row_version INTEGER NOT NULL DEFAULT 1)"
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _json(checkpoint: StreamCheckpoint) -> str:
        return json.dumps(
            {
                "positions": [
                    {"partition": item.partition, "offset": item.offset}
                    for item in checkpoint.positions
                ]
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _from_json(payload: str) -> StreamCheckpoint:
        value = json.loads(payload)
        if not isinstance(value, dict) or set(value) != {"positions"}:
            raise ValueError("stream checkpoint payload has invalid shape")
        positions = value["positions"]
        if not isinstance(positions, list):
            raise ValueError("stream checkpoint positions must be an array")
        parsed: list[StreamPosition] = []
        for item in positions:
            if not isinstance(item, dict) or set(item) != {"partition", "offset"}:
                raise ValueError("stream checkpoint position has invalid shape")
            partition = item["partition"]
            offset = item["offset"]
            if not isinstance(partition, int) or isinstance(partition, bool):
                raise ValueError("stream checkpoint partition must be integer")
            if not isinstance(offset, int) or isinstance(offset, bool):
                raise ValueError("stream checkpoint offset must be integer")
            parsed.append(StreamPosition(partition, offset))
        return StreamCheckpoint(tuple(parsed))

    def get(self, stream_id: str) -> StreamCheckpoint:
        if not stream_id or stream_id != stream_id.strip():
            raise ValueError("stream_id must be non-empty and trimmed")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT checkpoint_json FROM stream_checkpoints WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            return StreamCheckpoint() if row is None else self._from_json(row[0])
        finally:
            connection.close()

    def compare_and_set(
        self,
        stream_id: str,
        expected: StreamCheckpoint,
        next_checkpoint: StreamCheckpoint,
    ) -> bool:
        if not stream_id or stream_id != stream_id.strip():
            raise ValueError("stream_id must be non-empty and trimmed")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT checkpoint_digest FROM stream_checkpoints WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if row is None:
                if expected.positions:
                    connection.rollback()
                    return False
                connection.execute(
                    "INSERT INTO stream_checkpoints(stream_id,checkpoint_json,checkpoint_digest) "
                    "VALUES (?,?,?)",
                    (stream_id, self._json(next_checkpoint), next_checkpoint.digest),
                )
            else:
                if row[0] != expected.digest:
                    connection.rollback()
                    return False
                connection.execute(
                    "UPDATE stream_checkpoints SET checkpoint_json=?,checkpoint_digest=?,"
                    "row_version=row_version+1 WHERE stream_id=? AND checkpoint_digest=?",
                    (
                        self._json(next_checkpoint),
                        next_checkpoint.digest,
                        stream_id,
                        expected.digest,
                    ),
                )
                if connection.total_changes != 1:
                    connection.rollback()
                    return False
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ("SqliteStreamCheckpointStore",)
