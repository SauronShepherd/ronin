"""Initial PostgreSQL job/run persistence port.

This module deliberately exposes only the operations implemented here. It is
not wired as the production JobStore until the fenced attempt, event, result,
evidence and reclaim operations are complete.
"""

from __future__ import annotations

from typing import Any

from studio_orchestrator import Instant, Job, JobId, JobState, Page, Run

from studio_storage.memory import IdempotencyConflict
from studio_storage.pagination import decode_job_cursor, encode_job_cursor, validate_limit

from .postgres_core import PostgresDependencyError, _psycopg


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
