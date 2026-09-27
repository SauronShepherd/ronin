"""Durable notification delivery over the provider-neutral sink port."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from .notifications import NotificationIntent, NotificationSink


@dataclass(frozen=True)
class NotificationDispatchResult:
    attempted: int
    delivered: int
    failed: int


class NotificationIntentStore(Protocol):
    def list_pending_notification_intents(
        self, *, limit: int = 100, now: str | None = None
    ) -> tuple[NotificationIntent, ...]: ...
    def mark_notification_delivered(self, intent_id: str, *, delivered_at: str) -> bool: ...

    def record_notification_failure(
        self, notification_id: str, *, error: str, retry_at: str
    ) -> bool: ...


class NotificationDispatcher:
    """Deliver pending intents at-least-once; durable IDs make retries safe."""

    def __init__(
        self,
        store: NotificationIntentStore,
        sink: NotificationSink,
        *,
        clock: Callable[[], str],
        retry_delay_seconds: int = 30,
    ) -> None:
        if retry_delay_seconds < 1 or retry_delay_seconds > 86_400:
            raise ValueError("retry_delay_seconds must be between 1 and 86400")
        self._store = store
        self._sink = sink
        self._clock = clock
        self._retry_delay_seconds = retry_delay_seconds

    def _retry_at(self) -> str:
        current = datetime.fromisoformat(self._clock().replace("Z", "+00:00"))
        retry_at = current + timedelta(seconds=self._retry_delay_seconds)
        return retry_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def dispatch_once(self, *, limit: int = 100) -> NotificationDispatchResult:
        if limit < 1 or limit > 1000:
            raise ValueError("notification dispatch limit must be between 1 and 1000")
        pending = self._store.list_pending_notification_intents(limit=limit, now=self._clock())
        delivered = 0
        failed = 0
        for intent in pending:
            try:
                delivery_id = self._sink.send(intent)
                if delivery_id != intent.id:
                    raise ValueError("notification sink returned a different intent id")
            except Exception as exc:
                failed += 1
                # Keep dispatch at-least-once while making failures observable;
                # the store owns retry scheduling and backoff policy.
                record_failure = getattr(self._store, "record_notification_failure", None)
                if callable(record_failure):
                    record_failure(
                        intent.id,
                        error=str(exc) or "notification delivery failed",
                        retry_at=self._retry_at(),
                    )
                continue
            delivered += int(
                self._store.mark_notification_delivered(intent.id, delivered_at=self._clock())
            )
        return NotificationDispatchResult(len(pending), delivered, failed)


class SqliteNotificationIntentStore:
    """Durable intent queue used by the scheduler/alert notification bridge."""

    def __init__(self, path: Path) -> None:
        self._path = path
        with sqlite3.connect(path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notification_intents ("
                "id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL,"
                "created_at TEXT NOT NULL, delivered_at TEXT, last_error TEXT, retry_at TEXT)"
            )

    def enqueue(self, intent: NotificationIntent) -> bool:
        payload = json.dumps(
            {
                "id": intent.id,
                "kind": intent.kind,
                "title": intent.title,
                "body": intent.body,
                "created_at": str(intent.created_at),
                "attributes": list(intent.attributes),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with sqlite3.connect(self._path) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO notification_intents(id,payload,state,created_at) "
                "VALUES (?,?,?,?)",
                (intent.id, payload, "pending", str(intent.created_at)),
            )
        return cursor.rowcount == 1

    def list_pending_notification_intents(
        self, *, limit: int = 100, now: str | None = None
    ) -> tuple[NotificationIntent, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("notification dispatch limit must be between 1 and 1000")
        with sqlite3.connect(self._path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT payload FROM notification_intents WHERE state='pending' "
                "AND (retry_at IS NULL OR retry_at <= ?) "
                "ORDER BY created_at,id LIMIT ?",
                (now or "9999-12-31T23:59:59.999999Z", limit),
            ).fetchall()
        return tuple(
            NotificationIntent(
                item["id"],
                item["kind"],
                item["title"],
                item["body"],
                item["created_at"],
                tuple(tuple(pair) for pair in item["attributes"]),
            )
            for item in (json.loads(row["payload"]) for row in rows)
        )

    def mark_notification_delivered(self, intent_id: str, *, delivered_at: str) -> bool:
        with sqlite3.connect(self._path) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(
                "UPDATE notification_intents SET state='delivered',delivered_at=? "
                "WHERE id=? AND state='pending'",
                (delivered_at, intent_id),
            )
        return cursor.rowcount == 1

    def record_notification_failure(
        self, notification_id: str, *, error: str, retry_at: str
    ) -> bool:
        with sqlite3.connect(self._path) as connection:
            cursor = connection.execute(
                "UPDATE notification_intents SET last_error=?,retry_at=? "
                "WHERE id=? AND state='pending'",
                (error, retry_at, notification_id),
            )
        return cursor.rowcount == 1


__all__ = (
    "NotificationDispatcher",
    "NotificationDispatchResult",
    "NotificationIntentStore",
    "SqliteNotificationIntentStore",
)
