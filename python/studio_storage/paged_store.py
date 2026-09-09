"""Stable keyset pagination adapters for in-memory and bounded async storage."""

from __future__ import annotations

from functools import partial

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
from studio_storage.memory import InMemoryJobStore as _InMemoryJobStore
from studio_storage.pagination import (
    decode_cursor,
    decode_event_cursor,
    decode_job_cursor,
    encode_cursor,
    encode_event_cursor,
    encode_job_cursor,
    initial_event_cursor,
    validate_limit,
)

# Private compatibility aliases keep existing contract tests stable while cursor
# semantics live in one dedicated module instead of this adapter wrapper.
_encode_cursor = encode_cursor
_decode_cursor = decode_cursor
_encode_job_cursor = encode_job_cursor
_decode_job_cursor = decode_job_cursor
_encode_event_cursor = encode_event_cursor
_decode_event_cursor = decode_event_cursor
_initial_event_cursor = initial_event_cursor
_validate_limit = validate_limit


class InMemoryJobStore(_InMemoryJobStore):
    """Reference adapter with stable newest-first and Run-event keyset paging."""

    def get_run_id_for_job(self, job_id: JobId) -> RunId | None:
        with self._lock:
            matches = [run for run in self._runs.values() if run.job_id == job_id]
            if not matches:
                return None
            return max(matches, key=lambda run: run.ordinal).id

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        validate_limit(limit)
        after: tuple[Instant, str] | None = None
        if cursor is not None:
            created_at, job_id = decode_job_cursor(
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
                next_cursor = encode_job_cursor(
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
        validate_limit(limit)
        cursor = initial_event_cursor(run_id) if since is None else since
        next_sequence, after_ordinal, after_sequence = decode_event_cursor(cursor, run_id=run_id)
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
        next_since = encode_event_cursor(
            run_id=run_id,
            next_sequence=next_sequence + len(selected),
            attempt_ordinal=last_ordinal,
            attempt_sequence=last_event.sequence,
        )
        return EventPage(items, next_since)


class BoundedAsyncJobStore(_BoundedAsyncJobStore):
    """Bounded async facade extended with C0 service-read contracts."""

    async def get_run_id_for_job(self, job_id: JobId) -> RunId | None:
        return await self._call(partial(self._store.get_run_id_for_job, job_id))

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


__all__ = ("BoundedAsyncJobStore", "InMemoryJobStore")
