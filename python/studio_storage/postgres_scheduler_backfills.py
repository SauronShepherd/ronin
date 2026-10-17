"""PostgreSQL persistence for snapshot-safe scheduler backfills."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from studio_core import (
    Schedule,
    Trigger,
    WorkflowDefinition,
    WorkflowRun,
    WorkspaceId,
)
from studio_orchestrator import Instant

from .scheduler import _task_run_id
from .scheduler_backfill import (
    BackfillConflict,
    BackfillId,
    BackfillRequest,
    BackfillRun,
    _backfill_run_id,
    _minute_aligned,
    _request_from_row,
    _run_from_row,
)
from .scheduler_backfill_runtime import BackfillCapacityExhausted, BackfillPlan


class PostgresSchedulerBackfillMixin:
    """Backfill methods mixed into the shared PostgreSQL scheduler adapter."""

    def _connect(self) -> Any:
        return cast(Any, super())._connect()

    def _require_backfill_workspace(self, cursor: Any, workspace_id: WorkspaceId) -> None:
        cast(Any, self)._require_active_workspace(cursor, workspace_id)

    def create_backfill(
        self,
        workspace_id: WorkspaceId,
        request: BackfillRequest,
        *,
        now: Instant | str,
    ) -> BackfillRequest:
        if request.state != "pending":
            raise ValueError("new backfill requests must start pending")
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))",
                    (str(workspace_id), str(request.id)),
                )
                cursor.execute(
                    "SELECT 1 FROM ronin_schedules WHERE workspace_id=%s AND schedule_id=%s",
                    (str(workspace_id), str(request.schedule_id)),
                )
                if cursor.fetchone() is None:
                    raise BackfillConflict("backfill schedule does not exist")
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfills "
                    "WHERE workspace_id=%s AND backfill_id=%s FOR UPDATE",
                    (str(workspace_id), str(request.id)),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    found = _request_from_row(existing)
                    if found != request:
                        raise BackfillConflict("backfill id already exists with different content")
                    connection.commit()
                    return found
                cursor.execute(
                    "INSERT INTO ronin_scheduler_backfills(workspace_id,backfill_id,schedule_id,"
                    "start_at,end_at,state,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,'pending',%s,%s)",
                    (
                        str(workspace_id),
                        str(request.id),
                        str(request.schedule_id),
                        str(request.start_at),
                        str(request.end_at),
                        str(current),
                        str(current),
                    ),
                )
            connection.commit()
            return request
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_backfill(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillRequest | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfills "
                    "WHERE workspace_id=%s AND backfill_id=%s",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
            return None if row is None else _request_from_row(row)
        finally:
            connection.close()

    def cancel_backfill(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        now: Instant | str,
    ) -> BackfillRequest:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))",
                    (str(workspace_id), str(backfill_id)),
                )
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfills "
                    "WHERE workspace_id=%s AND backfill_id=%s FOR UPDATE",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(str(backfill_id))
                request = _request_from_row(row)
                if request.state == "completed":
                    raise BackfillConflict("completed backfill cannot be cancelled")
                if request.state != "cancelled":
                    cursor.execute(
                        "UPDATE ronin_scheduler_backfills SET state='cancelled',updated_at=%s,"
                        "row_version=row_version+1 WHERE workspace_id=%s AND backfill_id=%s",
                        (str(current), str(workspace_id), str(backfill_id)),
                    )
                    request = replace(request, state="cancelled")
            connection.commit()
            return request
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_backfill_plan(
        self,
        workspace_id: WorkspaceId,
        request: BackfillRequest,
        *,
        max_concurrency: int,
        now: Instant | str,
    ) -> BackfillPlan:
        if request.state != "pending":
            raise ValueError("new backfill requests must start pending")
        if max_concurrency < 1:
            raise ValueError("backfill max_concurrency must be positive")
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))",
                    (str(workspace_id), str(request.id)),
                )
                cursor.execute(
                    "SELECT schedule_json FROM ronin_schedules "
                    "WHERE workspace_id=%s AND schedule_id=%s FOR SHARE",
                    (str(workspace_id), str(request.schedule_id)),
                )
                schedule_row = cursor.fetchone()
                if schedule_row is None:
                    raise BackfillConflict("backfill schedule does not exist")
                schedule = Schedule.from_json(schedule_row["schedule_json"])
                cursor.execute(
                    "SELECT definition_json FROM ronin_workflows "
                    "WHERE workspace_id=%s AND workflow_id=%s FOR SHARE",
                    (str(workspace_id), str(schedule.workflow_id)),
                )
                workflow_row = cursor.fetchone()
                if workflow_row is None:
                    raise BackfillConflict("backfill workflow does not exist")
                workflow = WorkflowDefinition.from_json(workflow_row["definition_json"])
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfills "
                    "WHERE workspace_id=%s AND backfill_id=%s FOR UPDATE",
                    (str(workspace_id), str(request.id)),
                )
                existing = cursor.fetchone()
                result_request = request
                if existing is not None:
                    found = _request_from_row(existing)
                    result_request = found
                    if (found.schedule_id, found.start_at, found.end_at) != (
                        request.schedule_id,
                        request.start_at,
                        request.end_at,
                    ):
                        raise BackfillConflict("backfill id already exists with different content")
                    cursor.execute(
                        "SELECT * FROM ronin_scheduler_backfill_plans "
                        "WHERE workspace_id=%s AND backfill_id=%s FOR UPDATE",
                        (str(workspace_id), str(request.id)),
                    )
                    saved = cursor.fetchone()
                    if saved is not None:
                        plan = BackfillPlan(
                            found,
                            Schedule.from_json(saved["schedule_json"]),
                            WorkflowDefinition.from_json(saved["workflow_json"]),
                            None
                            if saved["cursor_at"] is None
                            else Instant(str(saved["cursor_at"])),
                            int(saved["max_concurrency"]),
                            bool(saved["generation_complete"]),
                        )
                        if plan.max_concurrency != max_concurrency:
                            raise BackfillConflict(
                                "backfill plan already exists with different content"
                            )
                        connection.commit()
                        return plan
                else:
                    cursor.execute(
                        "INSERT INTO ronin_scheduler_backfills(workspace_id,backfill_id,"
                        "schedule_id,start_at,end_at,state,created_at,updated_at) "
                        "VALUES (%s,%s,%s,%s,%s,'pending',%s,%s)",
                        (
                            str(workspace_id),
                            str(request.id),
                            str(request.schedule_id),
                            str(request.start_at),
                            str(request.end_at),
                            str(current),
                            str(current),
                        ),
                    )
                cursor.execute(
                    "INSERT INTO ronin_scheduler_backfill_plans(workspace_id,backfill_id,"
                    "schedule_json,workflow_json,cursor_at,max_concurrency,generation_complete,"
                    "created_at,updated_at) VALUES (%s,%s,%s,%s,NULL,%s,FALSE,%s,%s)",
                    (
                        str(workspace_id),
                        str(request.id),
                        schedule.to_json(),
                        workflow.to_json(),
                        max_concurrency,
                        str(current),
                        str(current),
                    ),
                )
            connection.commit()
            return BackfillPlan(result_request, schedule, workflow, None, max_concurrency, False)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_backfill_plan(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> BackfillPlan | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT b.*,p.schedule_json,p.workflow_json,p.cursor_at,"
                    "p.max_concurrency,p.generation_complete "
                    "FROM ronin_scheduler_backfills b JOIN ronin_scheduler_backfill_plans p "
                    "ON p.workspace_id=b.workspace_id AND p.backfill_id=b.backfill_id "
                    "WHERE b.workspace_id=%s AND b.backfill_id=%s",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            schedule = Schedule.from_json(row["schedule_json"])
            request = BackfillRequest(
                BackfillId(row["backfill_id"]),
                schedule.id,
                Instant(str(row["start_at"])),
                Instant(str(row["end_at"])),
                row["state"],
            )
            return BackfillPlan(
                request,
                schedule,
                WorkflowDefinition.from_json(row["workflow_json"]),
                None if row["cursor_at"] is None else Instant(str(row["cursor_at"])),
                int(row["max_concurrency"]),
                bool(row["generation_complete"]),
            )
        finally:
            connection.close()

    def count_active_backfill_runs(self, workspace_id: WorkspaceId, backfill_id: BackfillId) -> int:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM ronin_scheduler_backfill_runs r "
                    "LEFT JOIN ronin_workflow_runs w ON w.workspace_id=r.workspace_id "
                    "AND w.workflow_run_id=r.workflow_run_id "
                    "WHERE r.workspace_id=%s AND r.backfill_id=%s "
                    "AND (r.state='reserved' OR w.state IN ('pending','running','cancelling'))",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
            if row is None:
                raise AssertionError("backfill active-run query returned no row")
            return int(row["count"])
        finally:
            connection.close()

    def advance_backfill_cursor(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        through: Instant | str,
        generation_complete: bool,
        now: Instant | str,
    ) -> BackfillPlan:
        logical = Instant(through)
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT b.start_at,b.end_at,b.state,p.cursor_at,p.generation_complete "
                    "FROM ronin_scheduler_backfills b JOIN ronin_scheduler_backfill_plans p "
                    "ON p.workspace_id=b.workspace_id AND p.backfill_id=b.backfill_id "
                    "WHERE b.workspace_id=%s AND b.backfill_id=%s FOR UPDATE OF b,p",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(str(backfill_id))
                start, end = Instant(str(row["start_at"])), Instant(str(row["end_at"]))
                if row["state"] in {"completed", "cancelled"}:
                    raise BackfillConflict(f"cannot advance cursor for {row['state']} backfill")
                if not start <= logical <= end:
                    raise ValueError("backfill cursor must remain inside requested range")
                if row["cursor_at"] is not None and logical < Instant(str(row["cursor_at"])):
                    raise ValueError("backfill cursor must not move backwards")
                if row["generation_complete"] and not generation_complete:
                    raise BackfillConflict("completed backfill generation cannot be reopened")
                if generation_complete and logical != end:
                    raise ValueError("backfill generation can complete only at end_at")
                cursor.execute(
                    "UPDATE ronin_scheduler_backfill_plans SET cursor_at=%s,"
                    "generation_complete=%s,updated_at=%s "
                    "WHERE workspace_id=%s AND backfill_id=%s",
                    (
                        str(logical),
                        generation_complete,
                        str(current),
                        str(workspace_id),
                        str(backfill_id),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        updated = self.get_backfill_plan(workspace_id, backfill_id)
        if updated is None:
            raise AssertionError("backfill plan disappeared after cursor update")
        return updated

    def _reserve_snapshot_backfill_run(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        logical: Instant,
        *,
        now: Instant,
    ) -> BackfillRun:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT b.*,p.max_concurrency,p.generation_complete "
                    "FROM ronin_scheduler_backfills b "
                    "JOIN ronin_scheduler_backfill_plans p ON p.workspace_id=b.workspace_id "
                    "AND p.backfill_id=b.backfill_id "
                    "WHERE b.workspace_id=%s AND b.backfill_id=%s FOR UPDATE OF b",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(str(backfill_id))
                request = _request_from_row(row)
                if request.state in {"completed", "cancelled"}:
                    raise BackfillConflict(f"cannot reserve run for {request.state} backfill")
                if not request.start_at <= logical <= request.end_at:
                    raise ValueError("backfill logical_time is outside requested range")
                run_id = _backfill_run_id(workspace_id, backfill_id, logical)
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfill_runs "
                    "WHERE workspace_id=%s AND backfill_id=%s AND logical_time=%s FOR UPDATE",
                    (str(workspace_id), str(backfill_id), str(logical)),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    reserved = _run_from_row(workspace_id, existing)
                    if reserved.workflow_run_id != run_id:
                        raise BackfillConflict(
                            "backfill logical time maps to conflicting workflow run"
                        )
                    connection.commit()
                    return reserved
                if row["generation_complete"]:
                    raise BackfillConflict("completed backfill generation cannot add runs")
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM ronin_scheduler_backfill_runs r "
                    "LEFT JOIN ronin_workflow_runs w ON w.workspace_id=r.workspace_id "
                    "AND w.workflow_run_id=r.workflow_run_id "
                    "WHERE r.workspace_id=%s AND r.backfill_id=%s "
                    "AND (r.state='reserved' OR w.state IN ('pending','running','cancelling'))",
                    (str(workspace_id), str(backfill_id)),
                )
                active = cursor.fetchone()
                if active is None:
                    raise AssertionError("backfill active-run query returned no row")
                if int(active["count"]) >= int(row["max_concurrency"]):
                    raise BackfillCapacityExhausted(str(backfill_id))
                cursor.execute(
                    "INSERT INTO ronin_scheduler_backfill_runs(workspace_id,backfill_id,"
                    "logical_time,workflow_run_id,state,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,'reserved',%s,%s)",
                    (
                        str(workspace_id),
                        str(backfill_id),
                        str(logical),
                        str(run_id),
                        str(now),
                        str(now),
                    ),
                )
                if request.state == "pending":
                    cursor.execute(
                        "UPDATE ronin_scheduler_backfills SET state='running',updated_at=%s,"
                        "row_version=row_version+1 WHERE workspace_id=%s AND backfill_id=%s",
                        (str(now), str(workspace_id), str(backfill_id)),
                    )
            connection.commit()
            return BackfillRun(workspace_id, backfill_id, logical, run_id, "reserved")
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_snapshot_backfill_run(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        logical_time: Instant | str,
        now: Instant | str,
    ) -> BackfillRun:
        plan = self.get_backfill_plan(workspace_id, backfill_id)
        if plan is None:
            raise KeyError(str(backfill_id))
        logical = Instant(logical_time)
        if not _minute_aligned(logical):
            raise ValueError("backfill logical_time must be aligned to a UTC minute")
        current = Instant(now)
        reserved = self._reserve_snapshot_backfill_run(
            workspace_id, backfill_id, logical, now=current
        )
        if reserved.state == "created":
            return reserved
        trigger = Trigger(
            "backfill",
            f"backfill:{backfill_id}:{logical}",
            source_ref=f"schedule:{plan.schedule_snapshot.id}",
        )
        run = WorkflowRun(
            reserved.workflow_run_id,
            plan.workflow_snapshot.id,
            plan.workflow_snapshot,
            trigger,
        )
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))",
                    (str(workspace_id), str(run.id)),
                )
                cursor.execute(
                    "SELECT run_json FROM ronin_workflow_runs "
                    "WHERE workspace_id=%s AND workflow_run_id=%s FOR UPDATE",
                    (str(workspace_id), str(run.id)),
                )
                existing = cursor.fetchone()
                if existing is None:
                    cursor.execute(
                        "SELECT workflow_run_id FROM ronin_workflow_runs "
                        "WHERE workspace_id=%s AND workflow_id=%s AND trigger_key=%s",
                        (str(workspace_id), str(run.workflow_id), trigger.key),
                    )
                    if cursor.fetchone() is not None:
                        raise BackfillConflict(
                            "backfill trigger key maps to conflicting workflow run"
                        )
                    cursor.execute(
                        "INSERT INTO ronin_workflow_runs(workspace_id,workflow_run_id,"
                        "workflow_id,trigger_key,state,run_json,created_at,updated_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            str(workspace_id),
                            str(run.id),
                            str(run.workflow_id),
                            trigger.key,
                            run.state,
                            run.to_json(),
                            str(current),
                            str(current),
                        ),
                    )
                    for node in plan.workflow_snapshot.pipeline.nodes:
                        cursor.execute(
                            "INSERT INTO ronin_task_runs(workspace_id,task_run_id,"
                            "workflow_run_id,node_id,state,attempt_count,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,'pending',0,%s,%s)",
                            (
                                str(workspace_id),
                                str(_task_run_id(run.id, node.id.value)),
                                str(run.id),
                                node.id.value,
                                str(current),
                                str(current),
                            ),
                        )
                elif WorkflowRun.from_json(existing["run_json"]) != run:
                    raise BackfillConflict("backfill workflow run identity has conflicting content")
                cursor.execute(
                    "UPDATE ronin_scheduler_backfill_runs SET state='created',updated_at=%s "
                    "WHERE workspace_id=%s AND backfill_id=%s AND logical_time=%s",
                    (str(current), str(workspace_id), str(backfill_id), str(logical)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return BackfillRun(workspace_id, backfill_id, logical, run.id, "created")

    def complete_backfill(
        self,
        workspace_id: WorkspaceId,
        backfill_id: BackfillId,
        *,
        now: Instant | str,
    ) -> BackfillRequest:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_backfill_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfills "
                    "WHERE workspace_id=%s AND backfill_id=%s FOR UPDATE",
                    (str(workspace_id), str(backfill_id)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(str(backfill_id))
                request = _request_from_row(row)
                if request.state == "cancelled":
                    raise BackfillConflict("cancelled backfill cannot be completed")
                cursor.execute(
                    "SELECT generation_complete FROM ronin_scheduler_backfill_plans "
                    "WHERE workspace_id=%s AND backfill_id=%s FOR UPDATE",
                    (str(workspace_id), str(backfill_id)),
                )
                plan = cursor.fetchone()
                if plan is None or not plan["generation_complete"]:
                    raise BackfillConflict("backfill generation is not complete")
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM ronin_scheduler_backfill_runs r "
                    "LEFT JOIN ronin_workflow_runs w ON w.workspace_id=r.workspace_id "
                    "AND w.workflow_run_id=r.workflow_run_id "
                    "WHERE r.workspace_id=%s AND r.backfill_id=%s "
                    "AND (r.state='reserved' OR w.state IN ('pending','running','cancelling'))",
                    (str(workspace_id), str(backfill_id)),
                )
                active = cursor.fetchone()
                if active is None or int(active["count"]) != 0:
                    raise BackfillConflict("backfill still has active runs")
                if request.state != "completed":
                    cursor.execute(
                        "UPDATE ronin_scheduler_backfills SET state='completed',updated_at=%s,"
                        "row_version=row_version+1 WHERE workspace_id=%s AND backfill_id=%s",
                        (str(current), str(workspace_id), str(backfill_id)),
                    )
                    request = replace(request, state="completed")
            connection.commit()
            return request
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_backfill_runs(
        self, workspace_id: WorkspaceId, backfill_id: BackfillId
    ) -> tuple[BackfillRun, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM ronin_scheduler_backfill_runs "
                    "WHERE workspace_id=%s AND backfill_id=%s ORDER BY logical_time",
                    (str(workspace_id), str(backfill_id)),
                )
                rows = cursor.fetchall()
            return tuple(_run_from_row(workspace_id, row) for row in rows)
        finally:
            connection.close()


__all__ = ("PostgresSchedulerBackfillMixin",)
