"""Durable checkpoint-addressed stream table for the reference runtime."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .contracts import StreamBatch, StreamRecord


class SqliteStreamTable:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS stream_table (stream_id TEXT NOT NULL, partition_id INTEGER NOT NULL, offset_value INTEGER NOT NULL, timestamp_ms INTEGER, key_value TEXT, value_json TEXT NOT NULL, PRIMARY KEY(stream_id, partition_id, offset_value))")
            connection.commit()

    def append(self, stream_id: str, batch: StreamBatch) -> int:
        if not stream_id or stream_id != stream_id.strip():
            raise ValueError("stream_id must be non-empty and trimmed")
        with sqlite3.connect(self._path) as connection:
            inserted = 0
            for record in batch.records:
                cursor = connection.execute("INSERT OR IGNORE INTO stream_table VALUES (?,?,?,?,?,?)", (stream_id, record.partition, record.offset, record.timestamp_ms, record.key, json.dumps(dict(record.value), sort_keys=True, separators=(",", ":"))))
                inserted += cursor.rowcount
            connection.commit()
            return inserted

    def read(self, stream_id: str, *, limit: int = 10_000) -> tuple[StreamRecord, ...]:
        if limit < 1 or limit > 100_000:
            raise ValueError("stream table read limit must be between 1 and 100000")
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute("SELECT partition_id,offset_value,timestamp_ms,key_value,value_json FROM stream_table WHERE stream_id=? ORDER BY partition_id,offset_value LIMIT ?", (stream_id, limit)).fetchall()
        return tuple(StreamRecord(int(row[0]), int(row[1]), None if row[2] is None else int(row[2]), row[3], json.loads(row[4])) for row in rows)


__all__ = ["SqliteStreamTable"]
