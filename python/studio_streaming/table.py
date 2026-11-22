"""Durable checkpoint-addressed stream table for the reference runtime."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .contracts import StreamBatch, StreamRecord


class SqliteStreamTable:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Any = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS stream_table ("
            "stream_id TEXT NOT NULL, partition_id INTEGER NOT NULL, "
            "offset_value INTEGER NOT NULL, timestamp_ms INTEGER, "
            "key_value TEXT, value_json TEXT NOT NULL, "
            "PRIMARY KEY(stream_id, partition_id, offset_value))"
        )
        self._connection.commit()

    def append(self, stream_id: str, batch: StreamBatch) -> int:
        if not stream_id or stream_id != stream_id.strip():
            raise ValueError("stream_id must be non-empty and trimmed")
        connection = self._connection
        if not batch.records:
            return 0
        try:
            encoded = [
                (
                    record,
                    json.dumps(dict(record.value), sort_keys=True, separators=(",", ":")),
                )
                for record in batch.records
            ]
            parameters = [
                (
                    stream_id,
                    record.partition,
                    record.offset,
                    record.timestamp_ms,
                    record.key,
                    value_json,
                )
                for record, value_json in encoded
            ]
            insert_result = connection.executemany(
                "INSERT INTO stream_table VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(stream_id,partition_id,offset_value) DO NOTHING",
                parameters,
            )
            inserted = int(getattr(insert_result, "rowcount", insert_result))
            if inserted != len(parameters):
                predicates = " OR ".join(
                    "(partition_id=? AND offset_value=?)" for _record, _value in encoded
                )
                lookup: list[object] = [stream_id]
                for record, _value in encoded:
                    lookup.extend((record.partition, record.offset))
                existing_rows = connection.execute(
                    "SELECT partition_id,offset_value,timestamp_ms,key_value,value_json "
                    "FROM stream_table WHERE stream_id=? AND (" + predicates + ")",
                    lookup,
                ).fetchall()
                existing = {
                    (int(row[0]), int(row[1])): (row[2], row[3], row[4])
                    for row in existing_rows
                }
                for record, value_json in encoded:
                    stored = existing.get((record.partition, record.offset))
                    if stored != (record.timestamp_ms, record.key, value_json):
                        raise ValueError("stream table replay conflicts with an existing record")
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise

    def read(self, stream_id: str, *, limit: int = 10_000) -> tuple[StreamRecord, ...]:
        if limit < 1 or limit > 100_000:
            raise ValueError("stream table read limit must be between 1 and 100000")
        rows = self._connection.execute(
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

    def close(self) -> None:
        self._connection.close()


class _PostgresConnectionAdapter:
    def __init__(self, connection: object) -> None:
        self._connection = connection

    @staticmethod
    def _sql(statement: str) -> str:
        return statement.replace("?", "%s")

    def execute(self, statement: str, parameters: tuple[object, ...] = ()) -> object:
        return self._connection.execute(self._sql(statement), parameters)  # type: ignore[attr-defined]

    def executemany(self, statement: str, parameters: list[tuple[object, ...]]) -> int:
        cursor = self._connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.executemany(self._sql(statement), parameters)
            return int(cursor.rowcount)
        finally:
            cursor.close()

    def commit(self) -> None:
        self._connection.commit()  # type: ignore[attr-defined]

    def rollback(self) -> None:
        self._connection.rollback()  # type: ignore[attr-defined]

    def close(self) -> None:
        self._connection.close()  # type: ignore[attr-defined]


class PostgresStreamTable(SqliteStreamTable):
    """PostgreSQL-backed durable stream sink table."""

    def __init__(self, dsn: str) -> None:
        if not dsn or not dsn.strip():
            raise ValueError("PostgreSQL stream table DSN must be non-empty")
        self._dsn = dsn
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL streaming requires the psycopg package") from exc
        self._connection: _PostgresConnectionAdapter = _PostgresConnectionAdapter(
            psycopg.connect(dsn)
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS stream_table ("
            "stream_id TEXT NOT NULL, partition_id INTEGER NOT NULL, "
            "offset_value BIGINT NOT NULL, timestamp_ms BIGINT, "
            "key_value TEXT, value_json TEXT NOT NULL, "
            "PRIMARY KEY(stream_id, partition_id, offset_value))"
        )
        self._connection.commit()


__all__ = ["PostgresStreamTable", "SqliteStreamTable"]
