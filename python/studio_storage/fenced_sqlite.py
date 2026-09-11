"""Canonical lease-fenced SQLite adapter for durable job storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from threading import local
from typing import cast, overload

from studio_orchestrator import (
    AttemptId,
    AttemptState,
    EventPage,
    Instant,
    JobId,
    JobState,
    LeaseToken,
    Page,
    RunExecutionEvent,
    RunId,
    RunState,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)

from studio_storage.limits import MAX_EVIDENCE_REFS_PER_RUN
from studio_storage.pagination import (
    decode_event_cursor,
    decode_job_cursor,
    encode_event_cursor,
    encode_job_cursor,
    initial_event_cursor,
    validate_limit,
)
from studio_storage.sqlite import _SqliteLifecycleStore


class _BorrowedConnection:
    """Keep a thread-local SQLite connection open across store operations."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __getattr__(self, name: str) -> object:
        return getattr(self._connection, name)

    def close(self) -> None:
        return None


class SqliteJobStore(_SqliteLifecycleStore):
    """Supported SQLite JobStore with all worker writes and service paging.

    The internal lifecycle helper owns only shared migration/lifecycle reads and
    claims. Worker-originated mutations and service paging live exclusively on
    this supported adapter.
    """

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        self._connections = local()

    def _connect(self) -> sqlite3.Connection:
        connection = cast(
            sqlite3.Connection | None,
            getattr(self._connections, "connection", None),
        )
        if connection is None:
            connection = super()._connect()
            self._connections.connection = connection
        return cast(sqlite3.Connection, _BorrowedConnection(connection))

    @staticmethod
    def _active_attempt_row(
        connection: sqlite3.Connection,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> sqlite3.Row:
        row: sqlite3.Row | None = connection.execute(
            "SELECT a.*,r.job_id FROM attempts a JOIN runs r ON r.run_id=a.run_id "
            "WHERE a.attempt_id=? AND a.state IN ('leased','running') "
            "AND a.lease_owner=? AND a.lease_token=? AND a.lease_expires_at>?",
            (str(attempt_id), owner, str(lease_token), now),
        ).fetchone()
        if row is None:
            raise ValueError("attempt lease ownership lost")
        return row

    @staticmethod
    def _require_write_lease(
        *,
        owner: object,
        lease_token: object,
        now: object,
    ) -> tuple[str, LeaseToken, Instant]:
        """Reject the obsolete unfenced base-call shape before any mutation."""

        if not isinstance(owner, str) or not isinstance(lease_token, LeaseToken) or now is None:
            raise ValueError("worker write requires active lease")
        if not isinstance(now, (str, Instant)):
            raise TypeError("now must be an Instant or canonical string")
        return owner, lease_token, Instant(now)

    def get_run_id_for_job(self, job_id: JobId) -> RunId | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_id FROM runs WHERE job_id=? ORDER BY ordinal DESC LIMIT 1",
                (str(job_id),),
            ).fetchone()
            return None if row is None else RunId(row["run_id"])
        finally:
            connection.close()

    def list_jobs(
        self,
        *,
        project_id: str | None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        validate_limit(limit)
        clauses: list[str] = []
        values: list[object] = []
        if project_id is not None:
            clauses.append("project_id=?")
            values.append(project_id)
        if state is not None:
            clauses.append("state=?")
            values.append(state.value)
        if cursor is not None:
            created_at, job_id = decode_job_cursor(
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
            jobs = tuple(self.get_job(JobId(row["job_id"])) for row in rows[:limit])
            if any(job is None for job in jobs):
                raise AssertionError("listed job disappeared")
            items = tuple(job for job in jobs if job is not None)
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
        finally:
            connection.close()

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
        next_since = encode_event_cursor(
            run_id=run_id,
            next_sequence=next_sequence + len(selected),
            attempt_ordinal=int(last["ordinal"]),
            attempt_sequence=int(last["sequence"]),
        )
        return EventPage(items, next_since)

    @overload
    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
    ) -> None: ...

    @overload
    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None: ...

    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
        *,
        owner: str | None = None,
        lease_token: LeaseToken | None = None,
        now: Instant | str | None = None,
    ) -> None:
        owner, lease_token, current = self._require_write_lease(
            owner=owner,
            lease_token=lease_token,
            now=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._active_attempt_row(
                connection,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence),-1)+1 AS next_sequence FROM attempt_events "
                "WHERE attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
            if row is None:
                raise AssertionError("event sequence query returned no row")
            expected = int(row["next_sequence"])
            for event in events:
                if event.attempt_id != attempt_id or event.sequence != expected:
                    raise ValueError("event sequence must be contiguous within attempt")
                connection.execute(
                    "INSERT INTO attempt_events("
                    "attempt_id,sequence,event_type,message,occurred_at) VALUES (?,?,?,?,?)",
                    (str(attempt_id), event.sequence, event.kind, event.message, event.occurred_at),
                )
                expected += 1
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @overload
    def put_cell_result(self, result: StoredCellResult) -> None: ...

    @overload
    def put_cell_result(
        self,
        attempt_id: AttemptId,
        result: StoredCellResult,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None: ...

    def put_cell_result(self, *args: object, **kwargs: object) -> None:
        owner = kwargs.pop("owner", None)
        lease_token = kwargs.pop("lease_token", None)
        now = kwargs.pop("now", None)
        keyword_attempt = kwargs.pop("attempt_id", None)
        keyword_result = kwargs.pop("result", None)
        if kwargs:
            raise TypeError("unexpected put_cell_result arguments")

        if len(args) == 1 and keyword_attempt is None and keyword_result is None:
            if isinstance(args[0], StoredCellResult):
                raise ValueError("worker write requires active lease")
            raise TypeError("invalid put_cell_result arguments")
        if not args and keyword_attempt is None and isinstance(keyword_result, StoredCellResult):
            raise ValueError("worker write requires active lease")

        if len(args) == 2 and keyword_attempt is None and keyword_result is None:
            attempt_id, result = args
        elif not args and keyword_attempt is not None and keyword_result is not None:
            attempt_id, result = keyword_attempt, keyword_result
        else:
            raise TypeError("invalid put_cell_result arguments")
        if not isinstance(attempt_id, AttemptId) or not isinstance(result, StoredCellResult):
            raise TypeError("invalid put_cell_result arguments")

        owner, lease_token, current = self._require_write_lease(
            owner=owner,
            lease_token=lease_token,
            now=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._active_attempt_row(
                connection,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            if result.run_id.value != attempt["run_id"]:
                raise ValueError("cell result run does not match attempt")
            connection.execute(
                "INSERT INTO cell_results(run_id,cell_id,source_digest,execution_identity_digest,"
                "state,result_json,updated_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(run_id,cell_id) DO UPDATE SET source_digest=excluded.source_digest,"
                "execution_identity_digest=excluded.execution_identity_digest,state=excluded.state,"
                "result_json=excluded.result_json,updated_at=excluded.updated_at",
                (
                    str(result.run_id),
                    result.cell_id,
                    result.source_digest,
                    result.execution_identity_digest,
                    result.state,
                    result.result_json,
                    result.updated_at,
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @overload
    def put_evidence(self, ref: StoredEvidenceRef) -> None: ...

    @overload
    def put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None: ...

    def put_evidence(self, *args: object, **kwargs: object) -> None:
        owner = kwargs.pop("owner", None)
        lease_token = kwargs.pop("lease_token", None)
        now = kwargs.pop("now", None)
        keyword_attempt = kwargs.pop("attempt_id", None)
        keyword_ref = kwargs.pop("ref", None)
        if kwargs:
            raise TypeError("unexpected put_evidence arguments")

        if len(args) == 1 and keyword_attempt is None and keyword_ref is None:
            if isinstance(args[0], StoredEvidenceRef):
                raise ValueError("worker write requires active lease")
            raise TypeError("invalid put_evidence arguments")
        if not args and keyword_attempt is None and isinstance(keyword_ref, StoredEvidenceRef):
            raise ValueError("worker write requires active lease")

        if len(args) == 2 and keyword_attempt is None and keyword_ref is None:
            attempt_id, ref = args
        elif not args and keyword_attempt is not None and keyword_ref is not None:
            attempt_id, ref = keyword_attempt, keyword_ref
        else:
            raise TypeError("invalid put_evidence arguments")
        if not isinstance(attempt_id, AttemptId) or not isinstance(ref, StoredEvidenceRef):
            raise TypeError("invalid put_evidence arguments")

        owner, lease_token, current = self._require_write_lease(
            owner=owner,
            lease_token=lease_token,
            now=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._active_attempt_row(
                connection,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            if ref.run_id.value != attempt["run_id"]:
                raise ValueError("evidence run does not match attempt")
            connection.execute(
                "INSERT OR REPLACE INTO evidence_refs("
                "run_id,cell_id,role,digest_algorithm,digest,media_type,size_bytes,storage_ref,"
                "availability,unavailable_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(ref.run_id),
                    ref.cell_id,
                    ref.role,
                    ref.digest_algorithm,
                    ref.digest,
                    ref.media_type,
                    ref.size_bytes,
                    ref.storage_ref,
                    ref.availability.value,
                    ref.unavailable_reason,
                ),
            )
            count_row = connection.execute(
                "SELECT COUNT(*) AS count FROM evidence_refs WHERE run_id=?",
                (str(ref.run_id),),
            ).fetchone()
            if count_row is None or int(count_row["count"]) > MAX_EVIDENCE_REFS_PER_RUN:
                raise ValueError(
                    f"run evidence must contain at most {MAX_EVIDENCE_REFS_PER_RUN} references"
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def complete_attempt(
        self,
        attempt_id: AttemptId,
        *,
        state: AttemptState,
        failure_code: str | None,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        if not state.terminal:
            raise ValueError("attempt completion state must be terminal")
        current = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = self._active_attempt_row(
                connection,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            connection.execute(
                "UPDATE attempts SET state=?,failure_code=?,lease_owner=NULL,lease_token=NULL,"
                "lease_expires_at=NULL,updated_at=?,row_version=row_version+1 WHERE attempt_id=?",
                (state.value, failure_code, current, str(attempt_id)),
            )
            run_id = row["run_id"]
            job_id = row["job_id"]
            if state is AttemptState.ABANDONED:
                connection.execute(
                    "UPDATE runs SET state=?,not_before=?,updated_at=?,row_version=row_version+1 "
                    "WHERE run_id=?",
                    (RunState.PENDING.value, current, current, run_id),
                )
            elif state is AttemptState.SUCCEEDED:
                connection.execute(
                    "UPDATE runs SET state=?,updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (RunState.SUCCEEDED.value, current, run_id),
                )
                connection.execute(
                    "UPDATE jobs SET state=?,failure_code=NULL,updated_at=?,"
                    "row_version=row_version+1 WHERE job_id=?",
                    (JobState.SUCCEEDED.value, current, job_id),
                )
            elif state is AttemptState.CANCELLED:
                connection.execute(
                    "UPDATE runs SET state=?,updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (RunState.CANCELLED.value, current, run_id),
                )
                connection.execute(
                    "UPDATE jobs SET state=?,updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (JobState.CANCELLED.value, current, job_id),
                )
            else:
                connection.execute(
                    "UPDATE runs SET state=?,updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (RunState.FAILED.value, current, run_id),
                )
                connection.execute(
                    "UPDATE jobs SET state=?,failure_code=?,updated_at=?,row_version=row_version+1 "
                    "WHERE job_id=?",
                    (JobState.FAILED.value, failure_code, current, job_id),
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = ("SqliteJobStore",)
