"""Durable checkpoint-addressed stream table for the reference runtime."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .contracts import StreamBatch, StreamRecord


class SqliteStreamTable:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS stream_table ("
                "stream_id TEXT NOT NULL, partition_id INTEGER NOT NULL, "
                "offset_value INTEGER NOT NULL, timestamp_ms INTEGER, "
                "key_value TEXT, value_json TEXT NOT NULL, "
                "PRIMARY KEY(stream_id, partition_id, offset_value))"
            )
            connection.commit()

    def append(self, stream_id: str, batch: StreamBatch) -> int:
        if not stream_id or stream_id != stream_id.strip():
            raise ValueError("stream_id must be non-empty and trimmed")
        with closing(sqlite3.connect(self._path)) as connection, connection:
            inserted = 0
            for record in batch.records:
                value_json = json.dumps(dict(record.value), sort_keys=True, separators=(",", ":"))
                existing = connection.execute(
                    "SELECT timestamp_ms,key_value,value_json FROM stream_table "
                    "WHERE stream_id=? AND partition_id=? AND offset_value=?",
                    (stream_id, record.partition, record.offset),
                ).fetchone()
                if existing is not None:
                    if existing != (record.timestamp_ms, record.key, value_json):
                        raise ValueError("stream table replay conflicts with an existing record")
                    continue
                cursor = connection.execute(
                    "INSERT INTO stream_table VALUES (?,?,?,?,?,?)",
                    (
                        stream_id,
                        record.partition,
                        record.offset,
                        record.timestamp_ms,
                        record.key,
                        value_json,
                    ),
                )
                inserted += cursor.rowcount
            connection.commit()
            return inserted

    def read(self, stream_id: str, *, limit: int = 10_000) -> tuple[StreamRecord, ...]:
        if limit < 1 or limit > 100_000:
            raise ValueError("stream table read limit must be between 1 and 100000")
        with closing(sqlite3.connect(self._path)) as connection, connection:
            rows = connection.execute(
                "SELECT partition_id,offset_value,timestamp_ms,key_value,value_json "
                "FROM stream_table WHERE stream_id=? "
                "ORDER BY partition_id,offset_value LIMIT ?",
                (stream_id, limit),
            ).fetchall()
        return tuple(
            StreamRecord(
                int(row[0]),
                int(row[1]),
                None if row[2] is None else int(row[2]),
                row[3],
                json.loads(row[4]),
            )
            for row in rows
        )


__all__ = ["SqliteStreamTable"]
