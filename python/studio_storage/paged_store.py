"""Stable keyset pagination for durable jobs and Run-global events."""

from __future__ import annotations

import base64
import binascii
import json
from functools import partial
from typing import Any

from studio_orchestrator import (
    AttemptId,
    EventPage,
    Instant,
    JobId,
    JobState,
    Page,
    RunExecutionEvent,
    RunId,
    StoredExecutionEvent,
)

from studio_storage.async_store import BoundedAsyncJobStore as _BoundedAsyncJobStore
from studio_storage.fenced_sqlite import SqliteJobStore as _SqliteJobStore
from studio_storage.memory import InMemoryJobStore as _InMemoryJobStore

_CURSOR_VERSION = 1
_MAX_CURSOR_BYTES = 1024


def _encode_cursor(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    if not cursor or len(cursor.encode("utf-8")) > _MAX_CURSOR_BYTES:
        raise ValueError("invalid cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(decoded, dict):
        raise ValueError("invalid cursor")
    return decoded


def _job_state_value(state: JobState | None) -> str | None:
    return None if state is None else state.value


def _encode_job_cursor(
    *,
    created_at: Instant,
    job_id: JobId,
    project_id: str | None,
    state: JobState | None,
) -> str:
    return _encode_cursor(
        {
            "v": _CURSOR_VERSION,
            "kind": "jobs",
            "created_at": str(created_at),
            "job_id": str(job_id),
            "project_id": project_id,
            "state": _job_state_value(state),
        }
    )


def _decode_job_cursor(
    cursor: str,
    *,
    project_id: str | None,
    state: JobState | None,
) -> tuple[Instant, JobId]:
    payload = _decode_cursor(cursor)
    expected_keys = {"v", "kind", "created_at", "job_id", "project_id", "state"}
    if set(payload) != expected_keys or payload.get("v") != _CURSOR_VERSION:
        raise ValueError("invalid job cursor")
    if payload.get("kind") != "jobs":
        raise ValueError("invalid job cursor")
    if payload.get("project_id") != project_id or payload.get("state") != _job_state_value(state):
        raise ValueError("job cursor does not match filters")
    created_at = payload.get("created_at")
    job_id = payload.get("job_id")
    if not isinstance(created_at, str) or not isinstance(job_id, str) or not job_id:
        raise ValueError("invalid job cursor")
    try:
        return Instant(created_at), JobId(job_id)
    except ValueError as exc:
        raise ValueError("invalid job cursor") from exc


def _encode_event_cursor(
    *,
    run_id: RunId,
    next_sequence: int,
    attempt_ordinal: int,
    attempt_sequence: int,
) -> str:
    return _encode_cursor(
        {
            "v": _CURSOR_VERSION,
            "kind": "run-events",
            "run_id": str(run_id),
            "next_sequence": next_sequence,
            "attempt_ordinal": attempt_ordinal,
            "attempt_sequence": attempt_sequence,
        }
    )


def _initial_event_cursor(run_id: RunId) -> str:
    return _encode_event_cursor(
        run_id=run_id,
        next_sequence=0,
        attempt_ordinal=0,
        attempt_sequence=-1,
    )


def _decode_event_cursor(cursor: str, *, run_id: RunId) -> tuple[int, int, int]:
    payload = _decode_cursor(cursor)
    expected_keys = {
        "v",
        "kind",
        "run_id",
        "next_sequence",
        "attempt_ordinal",
        "attempt_sequence",
    }
    if set(payload) != expected_keys or payload.get("v") != _CURSOR_VERSION:
        raise ValueError("invalid event cursor")
    if payload.get("kind") != "run-events" or payload.get("run_id") != str(run_id):
        raise ValueError("event cursor does not match run")
    next_sequence = payload.get("next_sequence")
    attempt_ordinal = payload.get("attempt_ordinal")
    attempt_sequence = payload.get("attempt_sequence")
    if (
        not isinstance(next_sequence, int)
        or isinstance(next_sequence, bool)
        or next_sequence < 0
        or not isinstance(attempt_ordinal, int)
        or isinstance(attempt_ordinal, bool)
        or attempt_ordinal < 0
        or not isinstance(attempt_sequence, int)
        or isinstance(attempt_sequence, bool)
        or attempt_sequence < -1
        or (attempt_ordinal == 0 and attempt_sequence != -1)
        or (attempt_ordinal > 0 and attempt_sequence < 0)
    ):
        raise ValueError("invalid event cursor")
    return next_sequence, attempt_ordinal, attempt_sequence


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")


class InMemoryJobStore(_InMemoryJobStore):
    """Reference adapter with stable newest-first and Run-event keyset paging."""

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        _validate_limit(limit)
        after: tuple[Instant, str] | None = None
        if cursor is not None:
            created_at, job_id = _decode_job_cursor(
                cursor,
                project_id=project_id,
                state=state,
            )
            after = (created_at, str(job_id))
        with self._lock:
            filtered = [
                item
                for item in self._jobs.values()
                if (project_id is None or item.project_id == project_id)
                and (state is None or item.state is state)
                and (after is None or (item.created_at, str(item.id)) < after)
            ]
            filtered.sort(key=lambda item: (item.created_at, str(item.id)), reverse=True)
            rows = filtered[: limit + 1]
            items = tuple(rows[:limit])
            next_cursor = None
            if len(rows) > limit:
                last = items[-1]
                next_cursor = _encode_job_cursor(
                    created_at=last.created_at,
                    job_id=last.id,
                    project_id=project_id,
                    state=state,
                )
            return Page(items, next_cursor)

    def read_event_page(
        self,
        run_id: RunId,
        *,
        since: str | None,
        limit: int,
    ) -> EventPage:
        _validate_limit(limit)
        cursor = _initial_event_cursor(run_id) if since is None else since
        next_sequence, after_ordinal, after_sequence = _decode_event_cursor(cursor, run_id=run_id)
        with self._lock:
            attempts = sorted(
                (attempt for attempt in self._attempts.values() if attempt.run_id == run_id),
                key=lambda item: item.ordinal,
            )
            rows: list[tuple[int, StoredExecutionEvent]] = []
            for attempt in attempts:
                if attempt.ordinal < after_ordinal:
                    continue
                for event in self._events[attempt.id]:
                    if attempt.ordinal == after_ordinal and event.sequence <= after_sequence:
                        continue
                    rows.append((attempt.ordinal, event))
                    if len(rows) == limit + 1:
                        break
                if len(rows) == limit + 1:
                    break
        selected = rows[:limit]
        items = tuple(
            RunExecutionEvent(
                sequence=next_sequence + index,
                attempt_id=event.attempt_id,
                attempt_sequence=event.sequence,
                kind=event.kind,
                message=event.message,
                occurred_at=event.occurred_at,
            )
            for index, (_ordinal, event) in enumerate(selected)
        )
        if not selected:
            return EventPage(items, cursor)
        last_ordinal, last_event = selected[-1]
        next_since = _encode_event_cursor(
            run_id=run_id,
            next_sequence=next_sequence + len(selected),
            attempt_ordinal=last_ordinal,
            attempt_sequence=last_event.sequence,
        )
        return EventPage(items, next_since)


class SqliteJobStore(_SqliteJobStore):
    """SQLite adapter with stable newest-first and Run-event keyset paging."""

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        _validate_limit(limit)
        clauses: list[str] = []
        values: list[object] = []
        if project_id is not None:
            clauses.append("project_id=?")
            values.append(project_id)
        if state is not None:
            clauses.append("state=?")
            values.append(state.value)
        if cursor is not None:
            created_at, job_id = _decode_job_cursor(
                cursor,
                project_id=project_id,
                state=state,
            )
            clauses.append("(created_at < ? OR (created_at = ? AND job_id < ?))")
            values.extend((created_at, created_at, str(job_id)))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM jobs{where} "  # noqa: S608
                "ORDER BY created_at DESC,job_id DESC LIMIT ?",
                (*values, limit + 1),
            ).fetchall()
            items = tuple(self._inner.get_job(JobId(row["job_id"])) for row in rows[:limit])
            if any(item is None for item in items):
                raise AssertionError("listed job disappeared")
            jobs = tuple(item for item in items if item is not None)
            next_cursor = None
            if len(rows) > limit:
                last = jobs[-1]
                next_cursor = _encode_job_cursor(
                    created_at=last.created_at,
                    job_id=last.id,
                    project_id=project_id,
                    state=state,
                )
            return Page(jobs, next_cursor)
        finally:
            connection.close()

    def read_event_page(
        self,
        run_id: RunId,
        *,
        since: str | None,
        limit: int,
    ) -> EventPage:
        _validate_limit(limit)
        cursor = _initial_event_cursor(run_id) if since is None else since
        next_sequence, after_ordinal, after_sequence = _decode_event_cursor(cursor, run_id=run_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT a.ordinal,e.attempt_id,e.sequence,e.event_type,e.message,e.occurred_at "
                "FROM attempt_events e JOIN attempts a ON a.attempt_id=e.attempt_id "
                "WHERE a.run_id=? AND "
                "(a.ordinal > ? OR (a.ordinal = ? AND e.sequence > ?)) "
                "ORDER BY a.ordinal,e.sequence LIMIT ?",
                (str(run_id), after_ordinal, after_ordinal, after_sequence, limit + 1),
            ).fetchall()
        finally:
            connection.close()
        selected = rows[:limit]
        items = tuple(
            RunExecutionEvent(
                sequence=next_sequence + index,
                attempt_id=AttemptId(row["attempt_id"]),
                attempt_sequence=int(row["sequence"]),
                kind=row["event_type"],
                message=row["message"],
                occurred_at=row["occurred_at"],
            )
            for index, row in enumerate(selected)
        )
        if not selected:
            return EventPage(items, cursor)
        last = selected[-1]
        next_since = _encode_event_cursor(
            run_id=run_id,
            next_sequence=next_sequence + len(selected),
            attempt_ordinal=int(last["ordinal"]),
            attempt_sequence=int(last["sequence"]),
        )
        return EventPage(items, next_since)


class BoundedAsyncJobStore(_BoundedAsyncJobStore):
    """Bounded async facade extended with the C0 event-page read contract."""

    async def read_event_page(
        self,
        run_id: RunId,
        *,
        since: str | None,
        limit: int,
    ) -> EventPage:
        return await self._call(
            partial(self._store.read_event_page, run_id, since=since, limit=limit)
        )


__all__ = ("BoundedAsyncJobStore", "InMemoryJobStore", "SqliteJobStore")
