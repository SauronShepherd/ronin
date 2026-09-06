"""Transactional SQLite JobStore for the v0.1 single-node control plane."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from studio_orchestrator import (
    AttemptId,
    AttemptLimitExceeded,
    AttemptState,
    ClaimedRun,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Page,
    Run,
    RunId,
    RunState,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)
from studio_storage.memory import IdempotencyConflict

_SCHEMA_VERSION = 1


def _add_seconds(value: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed + timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def migrate(connection: sqlite3.Connection, *, now: str) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _SCHEMA_VERSION:
        raise RuntimeError(f"database schema {current} is newer than supported {_SCHEMA_VERSION}")
    if current == _SCHEMA_VERSION:
        return
    script = Path(__file__).with_name("migrations").joinpath("001_initial.sql").read_text(
        encoding="utf-8"
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.executescript(script)
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (_SCHEMA_VERSION, now),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=JobId(row["job_id"]),
        project_id=row["project_id"],
        idempotency_key=row["idempotency_key"],
        request_digest=row["request_digest"],
        state=JobState(row["state"]),
        failure_code=row["failure_code"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _run(row: sqlite3.Row) -> Run:
    return Run(
        id=RunId(row["run_id"]),
        job_id=JobId(row["job_id"]),
        ordinal=int(row["ordinal"]),
        state=RunState(row["state"]),
        not_before=row["not_before"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqliteJobStore:
    def __init__(self, path: Path, *, migration_now: str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def create_job(self, job: Job, run: Run) -> Job:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM jobs WHERE project_id=? AND idempotency_key=?",
                (job.project_id, job.idempotency_key),
            ).fetchone()
            if existing is not None:
                found = _job(existing)
                if found.request_digest != job.request_digest:
                    raise IdempotencyConflict(
                        "idempotency key already exists for different request"
                    )
                connection.execute("COMMIT")
                return found
            if run.job_id != job.id:
                raise ValueError("run must belong to job")
            connection.execute(
                "INSERT INTO jobs(job_id,project_id,idempotency_key,request_digest,state,failure_code,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(job.id),
                    job.project_id,
                    job.idempotency_key,
                    job.request_digest,
                    job.state.value,
                    job.failure_code,
                    job.created_at,
                    job.updated_at,
                ),
            )
            connection.execute(
                "INSERT INTO runs(run_id,job_id,ordinal,state,not_before,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    str(run.id),
                    str(run.job_id),
                    run.ordinal,
                    run.state.value,
                    run.not_before,
                    run.created_at,
                    run.updated_at,
                ),
            )
            connection.execute("COMMIT")
            return job
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_job(self, job_id: JobId) -> Job | None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (str(job_id),)).fetchone()
            return None if row is None else _job(row)
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
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        offset = int(cursor) if cursor is not None else 0
        clauses: list[str] = []
        values: list[object] = []
        if project_id is not None:
            clauses.append("project_id=?")
            values.append(project_id)
        if state is not None:
            clauses.append("state=?")
            values.append(state.value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM jobs{where} ORDER BY job_id LIMIT ? OFFSET ?",  # noqa: S608
                (*values, limit + 1, offset),
            ).fetchall()
            items = tuple(_job(row) for row in rows[:limit])
            next_cursor = str(offset + limit) if len(rows) > limit else None
            return Page(items, next_cursor)
        finally:
            connection.close()

    def request_cancel(self, job_id: JobId, *, now: str) -> Job:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if job_row is None:
                raise KeyError(str(job_id))
            job = _job(job_row)
            if job.state.terminal:
                connection.execute("COMMIT")
                return job
            active = connection.execute(
                "SELECT 1 FROM attempts a JOIN runs r ON r.run_id=a.run_id WHERE r.job_id=? AND a.state IN ('leased','running') LIMIT 1",
                (str(job_id),),
            ).fetchone()
            if active is None:
                connection.execute(
                    "UPDATE runs SET state='cancelled',updated_at=?,row_version=row_version+1 WHERE job_id=? AND state='pending'",
                    (now, str(job_id)),
                )
                connection.execute(
                    "UPDATE jobs SET state='cancelled',updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (now, str(job_id)),
                )
            else:
                connection.execute(
                    "UPDATE runs SET state='cancelling',updated_at=?,row_version=row_version+1 WHERE job_id=? AND state IN ('leased','running')",
                    (now, str(job_id)),
                )
                connection.execute(
                    "UPDATE jobs SET state='cancelling',updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (now, str(job_id)),
                )
            updated = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            connection.execute("COMMIT")
            if updated is None:
                raise AssertionError("updated job disappeared")
            return _job(updated)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def claim_next_run(
        self,
        *,
        owner: str,
        lease_token: LeaseToken,
        attempt_id: AttemptId,
        lease_seconds: int,
        now: str,
    ) -> ClaimedRun | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute(
                "SELECT r.* FROM runs r JOIN jobs j ON j.job_id=r.job_id WHERE r.state='pending' AND r.not_before<=? AND j.state='queued' ORDER BY r.not_before,r.run_id LIMIT 1",
                (now,),
            ).fetchone()
            if run_row is None:
                connection.execute("COMMIT")
                return None
            run = _run(run_row)
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (str(run.job_id),)
            ).fetchone()
            if job_row is None:
                raise AssertionError("run references missing job")
            job = _job(job_row)
            ordinal_row = connection.execute(
                "SELECT COALESCE(MAX(ordinal),0)+1 AS ordinal FROM attempts WHERE run_id=?",
                (str(run.id),),
            ).fetchone()
            ordinal = int(ordinal_row["ordinal"])
            if ordinal > 10:
                connection.execute(
                    "UPDATE runs SET state='failed',updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (now, str(run.id)),
                )
                connection.execute(
                    "UPDATE jobs SET state='failed',failure_code='attempt_limit_exceeded',updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (now, str(job.id)),
                )
                connection.execute("COMMIT")
                raise AttemptLimitExceeded("attempt limit exceeded")
            expiry = _add_seconds(now, lease_seconds)
            connection.execute(
                "INSERT INTO attempts(attempt_id,run_id,ordinal,state,lease_owner,lease_token,lease_expires_at,heartbeat_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(attempt_id),
                    str(run.id),
                    ordinal,
                    AttemptState.RUNNING.value,
                    owner,
                    str(lease_token),
                    expiry,
                    now,
                    now,
                    now,
                ),
            )
            updated_run = connection.execute(
                "UPDATE runs SET state='running',updated_at=?,row_version=row_version+1 WHERE run_id=? AND state='pending' RETURNING *",
                (now, str(run.id)),
            ).fetchone()
            if updated_run is None:
                raise RuntimeError("run claim lost compare-and-set")
            updated_job = connection.execute(
                "UPDATE jobs SET state='running',updated_at=?,row_version=row_version+1 WHERE job_id=? AND state='queued' RETURNING *",
                (now, str(job.id)),
            ).fetchone()
            if updated_job is None:
                raise RuntimeError("job claim lost compare-and-set")
            connection.execute("COMMIT")
            return ClaimedRun(
                job=_job(updated_job),
                run=_run(updated_run),
                attempt_id=attempt_id,
                attempt_ordinal=ordinal,
                lease_token=lease_token,
            )
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: str,
        now: str,
    ) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE attempts SET heartbeat_at=?,lease_expires_at=?,updated_at=?,row_version=row_version+1 WHERE attempt_id=? AND state IN ('leased','running') AND lease_owner=? AND lease_token=? AND lease_expires_at>?",
                (now, expires_at, now, str(attempt_id), owner, str(lease_token), now),
            )
            return cursor.rowcount == 1
        finally:
            connection.close()

    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence),-1)+1 AS next_sequence FROM attempt_events WHERE attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
            expected = int(row["next_sequence"])
            for event in events:
                if event.attempt_id != attempt_id or event.sequence != expected:
                    raise ValueError("event sequence must be contiguous within attempt")
                connection.execute(
                    "INSERT INTO attempt_events(attempt_id,sequence,event_type,message,occurred_at) VALUES (?,?,?,?,?)",
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

    def read_events(self, run_id: RunId, *, since: int) -> tuple[StoredExecutionEvent, ...]:
        if since < 0:
            raise ValueError("since must be non-negative")
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT e.attempt_id,e.sequence,e.event_type,e.message,e.occurred_at FROM attempt_events e JOIN attempts a ON a.attempt_id=e.attempt_id WHERE a.run_id=? ORDER BY a.ordinal,e.sequence LIMIT -1 OFFSET ?",
                (str(run_id), since),
            ).fetchall()
            return tuple(
                StoredExecutionEvent(
                    attempt_id=AttemptId(row["attempt_id"]),
                    sequence=int(row["sequence"]),
                    kind=row["event_type"],
                    message=row["message"],
                    occurred_at=row["occurred_at"],
                )
                for row in rows
            )
        finally:
            connection.close()

    def put_cell_result(self, result: StoredCellResult) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO cell_results(run_id,cell_id,source_digest,execution_identity_digest,state,result_json,updated_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(run_id,cell_id) DO UPDATE SET source_digest=excluded.source_digest,execution_identity_digest=excluded.execution_identity_digest,state=excluded.state,result_json=excluded.result_json,updated_at=excluded.updated_at",
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
        finally:
            connection.close()

    def read_cell_results(self, run_id: RunId) -> tuple[StoredCellResult, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM cell_results WHERE run_id=? ORDER BY cell_id", (str(run_id),)
            ).fetchall()
            return tuple(
                StoredCellResult(
                    run_id=RunId(row["run_id"]),
                    cell_id=row["cell_id"],
                    source_digest=row["source_digest"],
                    execution_identity_digest=row["execution_identity_digest"],
                    state=row["state"],
                    result_json=row["result_json"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            )
        finally:
            connection.close()

    def put_evidence(self, ref: StoredEvidenceRef) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO evidence_refs(run_id,cell_id,role,digest_algorithm,digest,media_type,size_bytes,storage_ref) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(ref.run_id),
                    ref.cell_id,
                    ref.role,
                    ref.digest_algorithm,
                    ref.digest,
                    ref.media_type,
                    ref.size_bytes,
                    ref.storage_ref,
                ),
            )
        finally:
            connection.close()

    def read_evidence(self, run_id: RunId) -> tuple[StoredEvidenceRef, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM evidence_refs WHERE run_id=? ORDER BY role,digest", (str(run_id),)
            ).fetchall()
            return tuple(
                StoredEvidenceRef(
                    run_id=RunId(row["run_id"]),
                    cell_id=row["cell_id"],
                    role=row["role"],
                    digest_algorithm=row["digest_algorithm"],
                    digest=row["digest"],
                    media_type=row["media_type"],
                    size_bytes=row["size_bytes"],
                    storage_ref=row["storage_ref"],
                )
                for row in rows
            )
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
        now: str,
    ) -> None:
        if not state.terminal:
            raise ValueError("attempt completion state must be terminal")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT a.*,r.job_id,r.state AS run_state,j.state AS job_state FROM attempts a JOIN runs r ON r.run_id=a.run_id JOIN jobs j ON j.job_id=r.job_id WHERE a.attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
            if row is None:
                raise KeyError(str(attempt_id))
            if (
                row["lease_owner"] != owner
                or row["lease_token"] != str(lease_token)
                or row["state"] not in {AttemptState.LEASED.value, AttemptState.RUNNING.value}
            ):
                raise ValueError("attempt lease ownership lost")
            connection.execute(
                "UPDATE attempts SET state=?,failure_code=?,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=?,row_version=row_version+1 WHERE attempt_id=?",
                (state.value, failure_code, now, str(attempt_id)),
            )
            run_id = row["run_id"]
            job_id = row["job_id"]
            if state is AttemptState.ABANDONED:
                connection.execute(
                    "UPDATE runs SET state='pending',not_before=?,updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (now, now, run_id),
                )
            elif state is AttemptState.SUCCEEDED:
                connection.execute(
                    "UPDATE runs SET state='succeeded',updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (now, run_id),
                )
                connection.execute(
                    "UPDATE jobs SET state='succeeded',failure_code=NULL,updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (now, job_id),
                )
            elif state is AttemptState.CANCELLED:
                connection.execute(
                    "UPDATE runs SET state='cancelled',updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (now, run_id),
                )
                connection.execute(
                    "UPDATE jobs SET state='cancelled',updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (now, job_id),
                )
            else:
                connection.execute(
                    "UPDATE runs SET state='failed',updated_at=?,row_version=row_version+1 WHERE run_id=?",
                    (now, run_id),
                )
                connection.execute(
                    "UPDATE jobs SET state='failed',failure_code=?,updated_at=?,row_version=row_version+1 WHERE job_id=?",
                    (failure_code, now, job_id),
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def reclaim_expired(self, *, now: str) -> tuple[RunId, ...]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT attempt_id,run_id FROM attempts WHERE state IN ('leased','running') AND lease_expires_at<=? ORDER BY run_id,ordinal",
                (now,),
            ).fetchall()
            run_ids: list[RunId] = []
            for row in rows:
                connection.execute(
                    "UPDATE attempts SET state='abandoned',lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=?,row_version=row_version+1 WHERE attempt_id=?",
                    (now, row["attempt_id"]),
                )
                connection.execute(
                    "UPDATE runs SET state='pending',not_before=?,updated_at=?,row_version=row_version+1 WHERE run_id=? AND state IN ('leased','running')",
                    (now, now, row["run_id"]),
                )
                run_ids.append(RunId(row["run_id"]))
            connection.execute("COMMIT")
            return tuple(run_ids)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = ["SqliteJobStore", "migrate", "open_database", "schema_version"]
