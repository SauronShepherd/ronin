"""PostgreSQL schedule cursors and idempotent fire records."""

from __future__ import annotations

from typing import Any, cast

from studio_core import Schedule, ScheduleId, Trigger, WorkflowRunId, WorkspaceId
from studio_orchestrator import Instant

from .scheduler import WorkflowNotFound
from .scheduler_schedule import (
    ScheduleFire,
    ScheduleFireConflict,
    _minute_aligned,
    _schedule_run_id,
)


class PostgresSchedulerScheduleMixin:
    """Durable cron cursor and fire operations for the PostgreSQL scheduler."""

    def _connect(self) -> Any:
        return cast(Any, super())._connect()

    def put_schedule(
        self, workspace_id: WorkspaceId, schedule: Schedule, *, now: Instant | str
    ) -> Schedule:
        current = Instant(now)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cast(Any, self)._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT 1 FROM ronin_workflows WHERE workspace_id=%s AND workflow_id=%s",
                    (str(workspace_id), str(schedule.workflow_id)),
                )
                if cursor.fetchone() is None:
                    raise WorkflowNotFound(str(schedule.workflow_id))
                cursor.execute(
                    "INSERT INTO ronin_schedules "
                    "(workspace_id,schedule_id,workflow_id,schedule_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (workspace_id,schedule_id) DO UPDATE SET "
                    "workflow_id=EXCLUDED.workflow_id,schedule_json=EXCLUDED.schedule_json,"
                    "updated_at=EXCLUDED.updated_at",
                    (
                        str(workspace_id),
                        str(schedule.id),
                        str(schedule.workflow_id),
                        schedule.to_json(),
                        str(current),
                        str(current),
                    ),
                )
            connection.commit()
            return schedule
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_schedule_cursor(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> Instant | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT last_evaluated_at FROM ronin_scheduler_schedule_cursors "
                    "WHERE workspace_id=%s AND schedule_id=%s",
                    (str(workspace_id), str(schedule_id)),
                )
                row = cursor.fetchone()
            return None if row is None else Instant(row["last_evaluated_at"])
        finally:
            connection.close()

    def advance_schedule_cursor(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        through: Instant | str,
        now: Instant | str,
    ) -> Instant:
        target = Instant(through)
        current = Instant(now)
        if not _minute_aligned(target):
            raise ValueError("schedule cursor must be aligned to a UTC minute")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s),hashtext(%s))",
                    (str(workspace_id), str(schedule_id)),
                )
                cast(Any, self)._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT 1 FROM ronin_schedules WHERE workspace_id=%s AND schedule_id=%s",
                    (str(workspace_id), str(schedule_id)),
                )
                if cursor.fetchone() is None:
                    raise KeyError(str(schedule_id))
                cursor.execute(
                    "SELECT last_evaluated_at FROM ronin_scheduler_schedule_cursors "
                    "WHERE workspace_id=%s AND schedule_id=%s FOR UPDATE",
                    (str(workspace_id), str(schedule_id)),
                )
                row = cursor.fetchone()
                if row is not None and Instant(row["last_evaluated_at"]) > target:
                    raise ValueError("schedule cursor must not move backwards")
                cursor.execute(
                    "INSERT INTO ronin_scheduler_schedule_cursors "
                    "(workspace_id,schedule_id,last_evaluated_at,updated_at) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (workspace_id,schedule_id) "
                    "DO UPDATE SET last_evaluated_at=EXCLUDED.last_evaluated_at,"
                    "updated_at=EXCLUDED.updated_at",
                    (str(workspace_id), str(schedule_id), str(target), str(current)),
                )
            connection.commit()
            return target
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fire_schedule(
        self,
        workspace_id: WorkspaceId,
        schedule_id: ScheduleId,
        *,
        scheduled_for: Instant | str,
        now: Instant | str,
    ) -> ScheduleFire:
        logical_time = Instant(scheduled_for)
        current = Instant(now)
        if not _minute_aligned(logical_time):
            raise ValueError("scheduled_for must be aligned to a UTC minute")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cast(Any, self)._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "SELECT schedule_json FROM ronin_schedules "
                    "WHERE workspace_id=%s AND schedule_id=%s FOR UPDATE",
                    (str(workspace_id), str(schedule_id)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(str(schedule_id))
                schedule = Schedule.from_json(row["schedule_json"])
                if not schedule.enabled:
                    raise ScheduleFireConflict("cannot fire a disabled schedule")
            trigger = Trigger(
                "schedule",
                f"schedule:{schedule.id}:{logical_time}",
                source_ref=f"schedule:{schedule.id}",
            )
            run_id = _schedule_run_id(workspace_id, schedule.id, logical_time)
            run = cast(Any, self).create_run(
                workspace_id,
                run_id,
                schedule.workflow_id,
                trigger,
                now=current,
            )
            fire = ScheduleFire(workspace_id, schedule.id, logical_time, run.id)
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_scheduler_schedule_fires "
                    "(workspace_id,schedule_id,scheduled_for,workflow_run_id,created_at) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT "
                    "(workspace_id,schedule_id,scheduled_for) DO NOTHING",
                    (
                        str(workspace_id),
                        str(schedule.id),
                        str(logical_time),
                        str(run.id),
                        str(current),
                    ),
                )
                cursor.execute(
                    "SELECT workflow_run_id FROM ronin_scheduler_schedule_fires "
                    "WHERE workspace_id=%s AND schedule_id=%s AND scheduled_for=%s",
                    (str(workspace_id), str(schedule.id), str(logical_time)),
                )
                row = cursor.fetchone()
                if row is None or row["workflow_run_id"] != str(run.id):
                    raise ScheduleFireConflict(
                        "logical schedule fire maps to conflicting workflow run"
                    )
            connection.commit()
            return fire
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_schedule_fires(
        self, workspace_id: WorkspaceId, schedule_id: ScheduleId
    ) -> tuple[ScheduleFire, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT scheduled_for,workflow_run_id FROM "
                    "ronin_scheduler_schedule_fires WHERE workspace_id=%s AND schedule_id=%s "
                    "ORDER BY scheduled_for",
                    (str(workspace_id), str(schedule_id)),
                )
                rows = cursor.fetchall()
            return tuple(
                ScheduleFire(
                    workspace_id,
                    schedule_id,
                    Instant(row["scheduled_for"]),
                    WorkflowRunId(row["workflow_run_id"]),
                )
                for row in rows
            )
        finally:
            connection.close()
