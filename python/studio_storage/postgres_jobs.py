"""Initial PostgreSQL job/run persistence port.

This module deliberately exposes only the operations implemented here. It is
not wired as the production JobStore until the fenced attempt, event, result,
evidence and reclaim operations are complete.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from studio_orchestrator import (
    AttemptId,
    AttemptLimitExceeded,
    AttemptState,
    ClaimedRun,
    EventPage,
    EvidenceAvailability,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseLost,
    LeaseToken,
    Page,
    Run,
    RunExecutionEvent,
    RunId,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)

from studio_storage.limits import MAX_EVIDENCE_REFS_PER_RUN
from studio_storage.memory import IdempotencyConflict
from studio_storage.pagination import (
    decode_event_cursor,
    decode_job_cursor,
    encode_event_cursor,
    encode_job_cursor,
    initial_event_cursor,
    validate_limit,
)

from .postgres_core import PostgresDependencyError, _psycopg


def _add_seconds(value: Instant | str, seconds: int) -> Instant:
    parsed = datetime.strptime(str(Instant(value)), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    return Instant((parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _job(row: dict[str, object]) -> Job:
    return Job(
        id=JobId(str(row["job_id"])),
        project_id=str(row["project_id"]),
        idempotency_key=str(row["idempotency_key"]),
        request_digest=str(row["request_digest"]),
        state=JobState(str(row["state"])),
        failure_code=None if row["failure_code"] is None else str(row["failure_code"]),
        created_at=Instant(str(row["created_at"])),
        updated_at=Instant(str(row["updated_at"])),
        target=str(row["target"]),
        parameters_json=str(row["parameters_json"]),
    )


class PostgresJobReadPort:
    """Transactional job/run create, lookup and filter-bound keyset paging."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-jobs") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name

    def _connect(self) -> Any:
        psycopg, dict_row = _psycopg()
        return psycopg.connect(
            self._dsn,
            autocommit=False,
            row_factory=dict_row,
            application_name=self._application_name,
        )

    def create_job(self, job: Job, run: Run) -> Job:
        if run.job_id != job.id:
            raise ValueError("run must belong to job")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_jobs WHERE project_id=%s "
                    "AND idempotency_key=%s FOR UPDATE",
                    (job.project_id, job.idempotency_key),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    found = _job(existing)
                    if found.request_digest != job.request_digest:
                        raise IdempotencyConflict(
                            "idempotency key already exists for different request"
                        )
                    connection.commit()
                    return found
                cursor.execute(
                    "INSERT INTO ronin_jobs(job_id,project_id,idempotency_key,request_digest,state,"
                    "failure_code,created_at,updated_at,target,parameters_json) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(job.id),
                        job.project_id,
                        job.idempotency_key,
                        job.request_digest,
                        job.state.value,
                        job.failure_code,
                        str(job.created_at),
                        str(job.updated_at),
                        job.target,
                        job.parameters_json,
                    ),
                )
                cursor.execute(
                    "INSERT INTO ronin_runs(run_id,job_id,ordinal,state,not_before,created_at,"
                    "updated_at)"
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(run.id),
                        str(run.job_id),
                        run.ordinal,
                        run.state.value,
                        str(run.not_before),
                        str(run.created_at),
                        str(run.updated_at),
                    ),
                )
            connection.commit()
            return job
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_job(self, job_id: JobId) -> Job | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM ronin_jobs WHERE job_id=%s", (str(job_id),))
                row = cursor.fetchone()
            connection.commit()
            return None if row is None else _job(row)
        finally:
            connection.close()

    def get_run_id_for_job(self, job_id: JobId) -> RunId | None:
        """Return the newest durable run id for a job, if it exists."""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_id FROM ronin_runs WHERE job_id=%s ORDER BY ordinal DESC LIMIT 1",
                    (str(job_id),),
                )
                row = cursor.fetchone()
            connection.commit()
            return None if row is None else RunId(str(row["run_id"]))
        finally:
            connection.close()

    def request_cancel(self, job_id: JobId, *, now: Instant | str) -> Job:
        """Request cancellation while serializing against worker state changes."""
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_jobs WHERE job_id=%s FOR UPDATE", (str(job_id),)
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(str(job_id))
                job = _job(row)
                if job.state.terminal:
                    connection.commit()
                    return job
                cursor.execute(
                    "SELECT 1 FROM ronin_attempts a "
                    "JOIN ronin_runs r ON r.run_id=a.run_id "
                    "WHERE r.job_id=%s AND a.state IN ('leased','running') LIMIT 1",
                    (str(job_id),),
                )
                active = cursor.fetchone() is not None
                if active:
                    cursor.execute(
                        "UPDATE ronin_runs SET state='cancelling',updated_at=%s,"
                        "row_version=row_version+1 WHERE job_id=%s "
                        "AND state IN ('leased','running')",
                        (str(current), str(job_id)),
                    )
                    next_state = "cancelling"
                else:
                    cursor.execute(
                        "UPDATE ronin_runs SET state='cancelled',updated_at=%s,"
                        "row_version=row_version+1 WHERE job_id=%s AND state='pending'",
                        (str(current), str(job_id)),
                    )
                    next_state = "cancelled"
                cursor.execute(
                    "UPDATE ronin_jobs SET state=%s,updated_at=%s,row_version=row_version+1 "
                    "WHERE job_id=%s",
                    (next_state, str(current), str(job_id)),
                )
                cursor.execute("SELECT * FROM ronin_jobs WHERE job_id=%s", (str(job_id),))
                updated = cursor.fetchone()
            connection.commit()
            if updated is None:
                raise AssertionError("updated job disappeared")
            return _job(updated)
        except Exception:
            connection.rollback()
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
        now: Instant | str,
    ) -> ClaimedRun | None:
        """Claim one pending run with PostgreSQL row-lock concurrency semantics."""
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT r.* FROM ronin_runs r JOIN ronin_jobs j ON j.job_id=r.job_id "
                    "WHERE r.state='pending' AND r.not_before<=%s "
                    "AND j.state IN ('queued','running') "
                    "ORDER BY r.not_before,r.run_id LIMIT 1 FOR UPDATE SKIP LOCKED",
                    (str(current),),
                )
                run_row = cursor.fetchone()
                if run_row is None:
                    connection.commit()
                    return None
                cursor.execute(
                    "SELECT * FROM ronin_jobs WHERE job_id=%s FOR UPDATE",
                    (str(run_row["job_id"]),),
                )
                job_row = cursor.fetchone()
                if job_row is None:
                    raise AssertionError("run references missing job")
                job = _job(job_row)
                cursor.execute(
                    "SELECT COALESCE(MAX(ordinal),0)+1 AS ordinal "
                    "FROM ronin_attempts WHERE run_id=%s",
                    (str(run_row["run_id"]),),
                )
                ordinal = int(cursor.fetchone()["ordinal"])
                if ordinal > 10:
                    cursor.execute(
                        "UPDATE ronin_runs SET state='failed',updated_at=%s,"
                        "row_version=row_version+1 WHERE run_id=%s AND state='pending'",
                        (str(current), str(run_row["run_id"])),
                    )
                    cursor.execute(
                        "UPDATE ronin_jobs SET state='failed',failure_code=%s,updated_at=%s,"
                        "row_version=row_version+1 WHERE job_id=%s",
                        ("attempt_limit_exceeded", str(current), str(job.id)),
                    )
                    connection.commit()
                    raise AttemptLimitExceeded("attempt limit exceeded")
                expiry = _add_seconds(current, lease_seconds)
                cursor.execute(
                    "INSERT INTO ronin_attempts(attempt_id,run_id,ordinal,state,lease_owner,"
                    "lease_token,lease_expires_at,heartbeat_at,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(attempt_id),
                        str(run_row["run_id"]),
                        ordinal,
                        AttemptState.RUNNING.value,
                        owner,
                        str(lease_token),
                        str(expiry),
                        str(current),
                        str(current),
                        str(current),
                    ),
                )
                cursor.execute(
                    "UPDATE ronin_runs SET state='running',updated_at=%s,"
                    "row_version=row_version+1 WHERE run_id=%s AND state='pending' "
                    "RETURNING *",
                    (str(current), str(run_row["run_id"])),
                )
                updated_run = cursor.fetchone()
                if updated_run is None:
                    raise RuntimeError("run claim lost compare-and-set")
                if job.state is JobState.QUEUED:
                    cursor.execute(
                        "UPDATE ronin_jobs SET state='running',updated_at=%s,"
                        "row_version=row_version+1 WHERE job_id=%s AND state='queued' "
                        "RETURNING *",
                        (str(current), str(job.id)),
                    )
                    updated_job = cursor.fetchone()
                else:
                    updated_job = job_row
            connection.commit()
            if updated_job is None:
                raise RuntimeError("job claim lost compare-and-set")
            from studio_orchestrator import RunState

            run = Run(
                id=RunId(str(updated_run["run_id"])),
                job_id=JobId(str(updated_run["job_id"])),
                ordinal=int(updated_run["ordinal"]),
                state=RunState(str(updated_run["state"])),
                not_before=Instant(str(updated_run["not_before"])),
                created_at=Instant(str(updated_run["created_at"])),
                updated_at=Instant(str(updated_run["updated_at"])),
            )
            return ClaimedRun(
                job=_job(updated_job),
                run=run,
                attempt_id=attempt_id,
                attempt_ordinal=ordinal,
                lease_token=lease_token,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat(
        self,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        expires_at: Instant | str,
        now: Instant | str,
    ) -> bool:
        """Renew an unexpired lease only for its current owner and token."""
        current = Instant(now)
        expiry = Instant(expires_at)
        if expiry <= current:
            raise ValueError("expires_at must be after now")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ronin_attempts SET heartbeat_at=%s,lease_expires_at=%s,"
                    "updated_at=%s,row_version=row_version+1 WHERE attempt_id=%s "
                    "AND state IN ('leased','running') AND lease_owner=%s "
                    "AND lease_token=%s AND lease_expires_at>%s",
                    (
                        str(current),
                        str(expiry),
                        str(current),
                        str(attempt_id),
                        owner,
                        str(lease_token),
                        str(current),
                    ),
                )
                renewed = cursor.rowcount == 1
            connection.commit()
            return bool(renewed)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_events(
        self,
        attempt_id: AttemptId,
        events: tuple[StoredExecutionEvent, ...],
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        """Append contiguous attempt events under the current write lease."""
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT state,lease_owner,lease_token,lease_expires_at "
                    "FROM ronin_attempts WHERE attempt_id=%s FOR UPDATE",
                    (str(attempt_id),),
                )
                attempt = cursor.fetchone()
                if (
                    attempt is None
                    or attempt["state"] not in {"leased", "running"}
                    or attempt["lease_owner"] != owner
                    or attempt["lease_token"] != str(lease_token)
                    or attempt["lease_expires_at"] is None
                    or Instant(str(attempt["lease_expires_at"])) <= current
                ):
                    raise LeaseLost("lease ownership no longer matches")
                cursor.execute(
                    "SELECT COALESCE(MAX(sequence),-1)+1 AS next_sequence "
                    "FROM ronin_attempt_events WHERE attempt_id=%s",
                    (str(attempt_id),),
                )
                expected = int(cursor.fetchone()["next_sequence"])
                for event in events:
                    if event.attempt_id != attempt_id or event.sequence != expected:
                        raise ValueError("event sequence must be contiguous within attempt")
                    cursor.execute(
                        "INSERT INTO ronin_attempt_events(attempt_id,sequence,event_type,"
                        "message,occurred_at) VALUES (%s,%s,%s,%s,%s)",
                        (
                            str(attempt_id),
                            event.sequence,
                            event.kind,
                            event.message,
                            str(event.occurred_at),
                        ),
                    )
                    expected += 1
                cursor.execute(
                    "UPDATE ronin_attempts SET updated_at=%s,row_version=row_version+1 "
                    "WHERE attempt_id=%s",
                    (str(current), str(attempt_id)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def put_cell_result(
        self,
        attempt_id: AttemptId,
        result: StoredCellResult,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        """Upsert a cell result only while the attempt lease is authoritative."""
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_id,state,lease_owner,lease_token,lease_expires_at "
                    "FROM ronin_attempts WHERE attempt_id=%s FOR UPDATE",
                    (str(attempt_id),),
                )
                attempt = cursor.fetchone()
                if (
                    attempt is None
                    or attempt["state"] not in {"leased", "running"}
                    or attempt["lease_owner"] != owner
                    or attempt["lease_token"] != str(lease_token)
                    or attempt["lease_expires_at"] is None
                    or Instant(str(attempt["lease_expires_at"])) <= current
                ):
                    raise LeaseLost("lease ownership no longer matches")
                if result.run_id != RunId(str(attempt["run_id"])):
                    raise ValueError("cell result run does not match attempt")
                cursor.execute(
                    "INSERT INTO ronin_cell_results(run_id,cell_id,source_digest,"
                    "execution_identity_digest,state,result_json,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(run_id,cell_id) DO UPDATE SET "
                    "source_digest=EXCLUDED.source_digest,"
                    "execution_identity_digest=EXCLUDED.execution_identity_digest,"
                    "state=EXCLUDED.state,result_json=EXCLUDED.result_json,"
                    "updated_at=EXCLUDED.updated_at",
                    (
                        str(result.run_id),
                        result.cell_id,
                        result.source_digest,
                        result.execution_identity_digest,
                        result.state,
                        result.result_json,
                        str(result.updated_at),
                    ),
                )
                cursor.execute(
                    "UPDATE ronin_attempts SET updated_at=%s,row_version=row_version+1 "
                    "WHERE attempt_id=%s",
                    (str(current), str(attempt_id)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        """Persist one evidence reference under a fenced attempt lease."""
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_id,state,lease_owner,lease_token,lease_expires_at "
                    "FROM ronin_attempts WHERE attempt_id=%s FOR UPDATE",
                    (str(attempt_id),),
                )
                attempt = cursor.fetchone()
                if (
                    attempt is None
                    or attempt["state"] not in {"leased", "running"}
                    or attempt["lease_owner"] != owner
                    or attempt["lease_token"] != str(lease_token)
                    or attempt["lease_expires_at"] is None
                    or Instant(str(attempt["lease_expires_at"])) <= current
                ):
                    raise LeaseLost("lease ownership no longer matches")
                if ref.run_id != RunId(str(attempt["run_id"])):
                    raise ValueError("evidence run does not match attempt")
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM ronin_evidence_refs WHERE run_id=%s",
                    (str(ref.run_id),),
                )
                if int(cursor.fetchone()["count"]) >= MAX_EVIDENCE_REFS_PER_RUN:
                    raise ValueError(
                        f"run evidence must contain at most {MAX_EVIDENCE_REFS_PER_RUN} references"
                    )
                cursor.execute(
                    "INSERT INTO ronin_evidence_refs(run_id,cell_id,role,digest_algorithm,"
                    "digest,media_type,size_bytes,storage_ref,availability,unavailable_reason) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
                cursor.execute(
                    "UPDATE ronin_attempts SET updated_at=%s,row_version=row_version+1 "
                    "WHERE attempt_id=%s",
                    (str(current), str(attempt_id)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read_events(self, run_id: RunId, *, since: int) -> tuple[StoredExecutionEvent, ...]:
        """Read attempt events for a run in deterministic attempt/sequence order."""
        if since < 0:
            raise ValueError("since must be non-negative")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT e.attempt_id,e.sequence,e.event_type,e.message,e.occurred_at "
                    "FROM ronin_attempt_events e JOIN ronin_attempts a "
                    "ON a.attempt_id=e.attempt_id WHERE a.run_id=%s "
                    "ORDER BY a.ordinal,e.sequence OFFSET %s",
                    (str(run_id), since),
                )
                rows = cursor.fetchall()
            connection.commit()
            return tuple(
                StoredExecutionEvent(
                    attempt_id=AttemptId(str(row["attempt_id"])),
                    sequence=int(row["sequence"]),
                    kind=str(row["event_type"]),
                    message=str(row["message"]),
                    occurred_at=Instant(str(row["occurred_at"])),
                )
                for row in rows
            )
        finally:
            connection.close()

    def read_event_page(self, run_id: RunId, *, since: str | None, limit: int) -> EventPage:
        """Read a bounded run-global event page using the shared opaque cursor."""
        validate_limit(limit)
        cursor = initial_event_cursor(run_id) if since is None else since
        next_sequence, after_ordinal, after_sequence = decode_event_cursor(cursor, run_id=run_id)
        connection = self._connect()
        try:
            with connection.cursor() as db:
                db.execute(
                    "SELECT a.ordinal,e.attempt_id,e.sequence,e.event_type,e.message,e.occurred_at "
                    "FROM ronin_attempt_events e JOIN ronin_attempts a "
                    "ON a.attempt_id=e.attempt_id WHERE a.run_id=%s AND "
                    "(a.ordinal>%s OR (a.ordinal=%s AND e.sequence>%s)) "
                    "ORDER BY a.ordinal,e.sequence LIMIT %s",
                    (str(run_id), after_ordinal, after_ordinal, after_sequence, limit + 1),
                )
                rows = list(db.fetchall())
            connection.commit()
        finally:
            connection.close()
        selected = rows[:limit]
        items = tuple(
            RunExecutionEvent(
                sequence=next_sequence + index,
                attempt_id=AttemptId(str(row["attempt_id"])),
                attempt_sequence=int(row["sequence"]),
                kind=str(row["event_type"]),
                message=str(row["message"]),
                occurred_at=Instant(str(row["occurred_at"])),
            )
            for index, row in enumerate(selected)
        )
        if not selected:
            return EventPage(items, cursor)
        last = selected[-1]
        return EventPage(
            items,
            encode_event_cursor(
                run_id=run_id,
                next_sequence=next_sequence + len(selected),
                attempt_ordinal=int(last["ordinal"]),
                attempt_sequence=int(last["sequence"]),
            ),
        )

    def read_cell_results(self, run_id: RunId) -> tuple[StoredCellResult, ...]:
        """Read all persisted cell results for a run in stable cell order."""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_cell_results WHERE run_id=%s ORDER BY cell_id",
                    (str(run_id),),
                )
                rows = cursor.fetchall()
            connection.commit()
            return tuple(
                StoredCellResult(
                    run_id=RunId(str(row["run_id"])),
                    cell_id=str(row["cell_id"]),
                    source_digest=str(row["source_digest"]),
                    execution_identity_digest=str(row["execution_identity_digest"]),
                    state=str(row["state"]),
                    result_json=str(row["result_json"]),
                    updated_at=Instant(str(row["updated_at"])),
                )
                for row in rows
            )
        finally:
            connection.close()

    def read_evidence(self, run_id: RunId) -> tuple[StoredEvidenceRef, ...]:
        """Read evidence references in the same stable order as SQLite."""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_evidence_refs WHERE run_id=%s "
                    "ORDER BY cell_id,role,availability,digest",
                    (str(run_id),),
                )
                rows = cursor.fetchall()
            connection.commit()
            return tuple(
                StoredEvidenceRef(
                    run_id=RunId(str(row["run_id"])),
                    cell_id=None if row["cell_id"] is None else str(row["cell_id"]),
                    role=str(row["role"]),
                    digest_algorithm=str(row["digest_algorithm"]),
                    digest=str(row["digest"]),
                    media_type=str(row["media_type"]),
                    size_bytes=int(row["size_bytes"]),
                    storage_ref=str(row["storage_ref"]),
                    availability=EvidenceAvailability(str(row["availability"])),
                    unavailable_reason=(
                        None
                        if row["unavailable_reason"] is None
                        else str(row["unavailable_reason"])
                    ),
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
        now: Instant | str,
    ) -> None:
        """Complete a fenced attempt and atomically project its terminal state."""
        if not state.terminal:
            raise ValueError("attempt completion state must be terminal")
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT a.run_id,r.job_id,a.state,a.lease_owner,a.lease_token,"
                    "a.lease_expires_at FROM ronin_attempts a "
                    "JOIN ronin_runs r ON r.run_id=a.run_id "
                    "WHERE a.attempt_id=%s FOR UPDATE",
                    (str(attempt_id),),
                )
                row = cursor.fetchone()
                if (
                    row is None
                    or row["state"] not in {"leased", "running"}
                    or row["lease_owner"] != owner
                    or row["lease_token"] != str(lease_token)
                    or row["lease_expires_at"] is None
                    or Instant(str(row["lease_expires_at"])) <= current
                ):
                    raise LeaseLost("lease ownership no longer matches")
                cursor.execute(
                    "UPDATE ronin_attempts SET state=%s,failure_code=%s,"
                    "lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,"
                    "updated_at=%s,row_version=row_version+1 WHERE attempt_id=%s",
                    (state.value, failure_code, str(current), str(attempt_id)),
                )
                run_id = str(row["run_id"])
                job_id = str(row["job_id"])
                if state is AttemptState.ABANDONED:
                    cursor.execute(
                        "UPDATE ronin_runs SET state='pending',not_before=%s,"
                        "updated_at=%s,row_version=row_version+1 WHERE run_id=%s",
                        (str(current), str(current), run_id),
                    )
                else:
                    run_state = {
                        AttemptState.SUCCEEDED: "succeeded",
                        AttemptState.CANCELLED: "cancelled",
                    }.get(state, "failed")
                    job_state = {
                        AttemptState.SUCCEEDED: "succeeded",
                        AttemptState.CANCELLED: "cancelled",
                    }.get(state, "failed")
                    cursor.execute(
                        "UPDATE ronin_runs SET state=%s,updated_at=%s,"
                        "row_version=row_version+1 WHERE run_id=%s",
                        (run_state, str(current), run_id),
                    )
                    cursor.execute(
                        "UPDATE ronin_jobs SET state=%s,failure_code=%s,updated_at=%s,"
                        "row_version=row_version+1 WHERE job_id=%s",
                        (
                            job_state,
                            None if state is not AttemptState.FAILED else failure_code,
                            str(current),
                            job_id,
                        ),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reclaim_expired(self, *, now: Instant | str) -> tuple[RunId, ...]:
        """Abandon expired leases and return their runs to the pending queue."""
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT attempt_id,run_id FROM ronin_attempts "
                    "WHERE state IN ('leased','running') AND lease_expires_at<=%s "
                    "ORDER BY run_id,ordinal FOR UPDATE SKIP LOCKED",
                    (str(current),),
                )
                rows = cursor.fetchall()
                run_ids: list[RunId] = []
                for row in rows:
                    cursor.execute(
                        "UPDATE ronin_attempts SET state='abandoned',failure_code=%s,"
                        "lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,"
                        "updated_at=%s,row_version=row_version+1 WHERE attempt_id=%s",
                        ("lease_expired", str(current), str(row["attempt_id"])),
                    )
                    cursor.execute(
                        "UPDATE ronin_runs SET state='pending',not_before=%s,"
                        "updated_at=%s,row_version=row_version+1 "
                        "WHERE run_id=%s AND state IN ('leased','running')",
                        (str(current), str(current), str(row["run_id"])),
                    )
                    run_ids.append(RunId(str(row["run_id"])))
            connection.commit()
            return tuple(run_ids)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_jobs(
        self,
        *,
        project_id: str | None,
        project_ids: tuple[str, ...] | None = None,
        state: JobState | None,
        limit: int,
        cursor: str | None,
    ) -> Page:
        validate_limit(limit)
        after: tuple[Instant, JobId] | None = None
        if cursor is not None:
            after = decode_job_cursor(
                cursor, project_id=project_id, project_ids=project_ids, state=state
            )
        connection = self._connect()
        try:
            with connection.cursor() as db:
                clauses = []
                values: list[object] = []
                if project_id is not None:
                    clauses.append("project_id=%s")
                    values.append(project_id)
                if project_ids is not None:
                    clauses.append("project_id = ANY(%s)")
                    values.append(list(project_ids))
                if state is not None:
                    clauses.append("state=%s")
                    values.append(state.value)
                if after is not None:
                    clauses.append("(created_at, job_id) < (%s, %s)")
                    values.extend((str(after[0]), after[1]))
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                db.execute(  # noqa: S608 - clauses are fixed SQL fragments
                    "SELECT * FROM ronin_jobs"  # noqa: S608 - fixed SQL fragments only
                    + where
                    + " ORDER BY created_at DESC, job_id DESC LIMIT %s",
                    (*values, limit + 1),
                )
                rows = list(db.fetchall())
            connection.commit()
            jobs = tuple(_job(row) for row in rows[:limit])
            next_cursor = None
            if len(rows) > limit:
                last = jobs[-1]
                next_cursor = encode_job_cursor(
                    created_at=last.created_at,
                    job_id=last.id,
                    project_id=project_id,
                    project_ids=project_ids,
                    state=state,
                )
            return Page(jobs, next_cursor)
        finally:
            connection.close()


__all__ = ("PostgresDependencyError", "PostgresJobReadPort")
