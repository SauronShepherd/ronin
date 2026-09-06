"""Lease-fenced SQLite adapter for worker-originated durable mutations."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from studio_orchestrator import (
    AttemptId,
    AttemptState,
    Instant,
    JobState,
    LeaseToken,
    RunState,
    StoredCellResult,
    StoredEvidenceRef,
    StoredExecutionEvent,
)

from studio_storage.sqlite import SqliteJobStore as _BaseSqliteJobStore


class SqliteJobStore(_BaseSqliteJobStore):
    """SQLite store whose worker writes are fenced by the active Attempt lease."""

    @staticmethod
    def _active_attempt_row(
        connection: sqlite3.Connection,
        attempt_id: AttemptId,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT a.*,r.job_id FROM attempts a JOIN runs r ON r.run_id=a.run_id "
            "WHERE a.attempt_id=? AND a.state IN ('leased','running') "
            "AND a.lease_owner=? AND a.lease_token=? AND a.lease_expires_at>?",
            (str(attempt_id), owner, str(lease_token), now),
        ).fetchone()
        if row is None:
            raise ValueError("attempt lease ownership lost")
        return row

    def append_events(
        self,
        attempt_id: AttemptId,
        events: Sequence[StoredExecutionEvent],
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        current = Instant(now)
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

    def put_cell_result(
        self,
        attempt_id: AttemptId,
        result: StoredCellResult,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        current = Instant(now)
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

    def put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        current = Instant(now)
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
                "INSERT OR REPLACE INTO evidence_refs(run_id,cell_id,role,digest_algorithm,digest,"
                "media_type,size_bytes,storage_ref) VALUES (?,?,?,?,?,?,?,?)",
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
