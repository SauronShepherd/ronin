"""Durable compilation reports and outbox records for Data Enginerring Studio."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from studio_storage.sqlite import open_database

from .compiler import CompilationReport


class SqliteCompilationStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        connection = open_database(path)
        try:
            self._migrate(connection)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS de_compilation_reports ("
            "revision_key TEXT NOT NULL, runtime TEXT NOT NULL, ir_digest TEXT NOT NULL,"
            "portable INTEGER NOT NULL, report_json TEXT NOT NULL, created_at TEXT NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(revision_key,runtime,ir_digest))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS de_outbox ("
            "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, aggregate_key TEXT NOT NULL,"
            "payload_json TEXT NOT NULL, published_at TEXT NULL, created_at TEXT NOT NULL "
            "DEFAULT CURRENT_TIMESTAMP)"
        )

    def save_report(
        self,
        *,
        revision_key: str,
        ir_digest: str,
        report: CompilationReport,
    ) -> None:
        payload = {
            "runtime": report.runtime,
            "portable": report.portable,
            "node_count": report.node_count,
            "edge_count": report.edge_count,
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "path": item.path,
                    "severity": item.severity,
                }
                for item in report.diagnostics
            ],
        }
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO de_compilation_reports "
                "(revision_key,runtime,ir_digest,portable,report_json) VALUES (?,?,?,?,?)",
                (
                    revision_key,
                    report.runtime,
                    ir_digest,
                    int(report.portable),
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
        finally:
            connection.close()

    def get_report(
        self, *, revision_key: str, runtime: str, ir_digest: str
    ) -> Mapping[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT report_json FROM de_compilation_reports WHERE revision_key=? "
                "AND runtime=? AND ir_digest=?",
                (revision_key, runtime, ir_digest),
            ).fetchone()
            return None if row is None else json.loads(row["report_json"])
        finally:
            connection.close()

    def get_latest_report(
        self, *, revision_key: str, runtime: str
    ) -> Mapping[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT report_json,ir_digest FROM de_compilation_reports "
                "WHERE revision_key=? AND runtime=? ORDER BY created_at DESC LIMIT 1",
                (revision_key, runtime),
            ).fetchone()
            if row is None:
                return None
            report = json.loads(row["report_json"])
            report["ir_digest"] = row["ir_digest"]
            return report
        finally:
            connection.close()

    def enqueue(
        self,
        *,
        event_id: str,
        event_type: str,
        aggregate_key: str,
        payload: Mapping[str, object],
    ) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO de_outbox(event_id,event_type,aggregate_key,payload_json) "
                "VALUES (?,?,?,?)",
                (
                    event_id,
                    event_type,
                    aggregate_key,
                    json.dumps(dict(payload), sort_keys=True, separators=(",", ":")),
                ),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def pending_events(self, *, limit: int = 100) -> tuple[dict[str, object], ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT event_id,event_type,aggregate_key,payload_json FROM de_outbox "
                "WHERE published_at IS NULL ORDER BY created_at,event_id LIMIT ?",
                (limit,),
            ).fetchall()
            return tuple(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "aggregate_key": row["aggregate_key"],
                    "payload": json.loads(row["payload_json"]),
                }
                for row in rows
            )
        finally:
            connection.close()

    def mark_published(self, event_id: str) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE de_outbox SET published_at=CURRENT_TIMESTAMP "
                "WHERE event_id=? AND published_at IS NULL",
                (event_id,),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()


async def publish_pending_compilation_events(
    store: SqliteCompilationStore,
    publish: Callable[[Mapping[str, object]], Awaitable[None]],
    *,
    limit: int = 100,
) -> tuple[str, ...]:
    """Publish pending events and acknowledge only after the transport succeeds.

    A failed callback leaves the event pending, so the next invocation retries it.
    The event id is stable and consumers can deduplicate it at their inbox.
    """
    published: list[str] = []
    for event in store.pending_events(limit=limit):
        await publish(event)
        if store.mark_published(str(event["event_id"])):
            published.append(str(event["event_id"]))
    return tuple(published)


__all__ = ("SqliteCompilationStore", "publish_pending_compilation_events")
