"""PostgreSQL workflow and schedule adapter for the local appliance."""

from __future__ import annotations

from typing import Any

from studio_core import Schedule, ScheduleId, WorkflowDefinition, WorkflowId, WorkspaceId
from studio_orchestrator import Instant

from .bundle_workflow_import_port import WorkflowBundleImportCommit, WorkflowBundleImportConflict
from .postgres_core import PostgresMetadataStore


class PostgresWorkflowBundleImportStore(PostgresMetadataStore):
    """Shared PostgreSQL adapter for workspace metadata and portable workflows."""

    @staticmethod
    def _require_active_workspace(cursor: Any, workspace_id: WorkspaceId) -> None:
        cursor.execute(
            "SELECT archived_at FROM ronin_workspaces WHERE workspace_id=%s",
            (str(workspace_id),),
        )
        row = cursor.fetchone()
        if row is None:
            raise WorkflowBundleImportConflict("target workspace does not exist")
        if row["archived_at"] is not None:
            raise WorkflowBundleImportConflict("target workspace is archived")

    def put_workflow(
        self,
        workspace_id: WorkspaceId,
        workflow: WorkflowDefinition,
        *,
        now: Instant | str,
    ) -> WorkflowDefinition:
        payload = workflow.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                cursor.execute(
                    "INSERT INTO ronin_workflows "
                    "(workspace_id,workflow_id,definition_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (workspace_id,workflow_id) DO UPDATE SET "
                    "definition_json=EXCLUDED.definition_json,updated_at=EXCLUDED.updated_at",
                    (str(workspace_id), str(workflow.id), payload, str(now), str(now)),
                )
            connection.commit()
            return workflow
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_workflow(
        self, workspace_id: WorkspaceId, workflow_id: WorkflowId
    ) -> WorkflowDefinition | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_workflows "
                    "WHERE workspace_id=%s AND workflow_id=%s",
                    (str(workspace_id), str(workflow_id)),
                )
                row = cursor.fetchone()
            return None if row is None else WorkflowDefinition.from_json(row["definition_json"])
        finally:
            connection.close()

    def list_workflows(self, workspace_id: WorkspaceId) -> tuple[WorkflowDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT definition_json FROM ronin_workflows "
                    "WHERE workspace_id=%s ORDER BY workflow_id",
                    (str(workspace_id),),
                )
                rows = cursor.fetchall()
            return tuple(WorkflowDefinition.from_json(row["definition_json"]) for row in rows)
        finally:
            connection.close()

    def list_schedules(self, workspace_id: WorkspaceId) -> tuple[Schedule, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT schedule_json FROM ronin_schedules "
                    "WHERE workspace_id=%s ORDER BY schedule_id",
                    (str(workspace_id),),
                )
                rows = cursor.fetchall()
            return tuple(Schedule.from_json(row["schedule_json"]) for row in rows)
        finally:
            connection.close()

    def get_schedule(self, workspace_id: WorkspaceId, schedule_id: ScheduleId) -> Schedule | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT schedule_json FROM ronin_schedules "
                    "WHERE workspace_id=%s AND schedule_id=%s",
                    (str(workspace_id), str(schedule_id)),
                )
                row = cursor.fetchone()
            return None if row is None else Schedule.from_json(row["schedule_json"])
        finally:
            connection.close()

    def commit_workflow_import(
        self,
        workspace_id: WorkspaceId,
        workflows: tuple[WorkflowDefinition, ...],
        schedules: tuple[Schedule, ...],
        *,
        now: Instant | str,
    ) -> WorkflowBundleImportCommit:
        workflow_ids = {item.id for item in workflows}
        schedule_ids = [item.id for item in schedules]
        if len(schedule_ids) != len(set(schedule_ids)):
            raise ValueError("workflow import schedules must have unique ids")
        if any(schedule.workflow_id not in workflow_ids for schedule in schedules):
            raise ValueError(
                "workflow import schedule must reference an imported workflow definition"
            )
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._require_active_workspace(cursor, workspace_id)
                created_workflows = 0
                for workflow in sorted(workflows, key=lambda item: item.id.value):
                    payload = workflow.to_json()
                    cursor.execute(
                        "SELECT definition_json FROM ronin_workflows "
                        "WHERE workspace_id=%s AND workflow_id=%s FOR UPDATE",
                        (str(workspace_id), str(workflow.id)),
                    )
                    existing = cursor.fetchone()
                    if existing is None:
                        cursor.execute(
                            "INSERT INTO ronin_workflows "
                            "(workspace_id,workflow_id,definition_json,created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s)",
                            (str(workspace_id), str(workflow.id), payload, str(now), str(now)),
                        )
                        created_workflows += 1
                    elif existing["definition_json"] != payload:
                        raise WorkflowBundleImportConflict(
                            "workflow id already exists with different portable "
                            f"definition: {workflow.id}"
                        )
                created_schedules = 0
                for schedule in sorted(schedules, key=lambda item: item.id.value):
                    payload = schedule.to_json()
                    cursor.execute(
                        "SELECT schedule_json FROM ronin_schedules "
                        "WHERE workspace_id=%s AND schedule_id=%s FOR UPDATE",
                        (str(workspace_id), str(schedule.id)),
                    )
                    existing = cursor.fetchone()
                    if existing is None:
                        cursor.execute(
                            "INSERT INTO ronin_schedules "
                            "(workspace_id,schedule_id,workflow_id,schedule_json,"
                            "created_at,updated_at) "
                            "VALUES (%s,%s,%s,%s,%s,%s)",
                            (
                                str(workspace_id),
                                str(schedule.id),
                                str(schedule.workflow_id),
                                payload,
                                str(now),
                                str(now),
                            ),
                        )
                        created_schedules += 1
                    elif existing["schedule_json"] != payload:
                        raise WorkflowBundleImportConflict(
                            "schedule id already exists with different portable "
                            f"definition: {schedule.id}"
                        )
            connection.commit()
            return WorkflowBundleImportCommit(created_workflows, created_schedules)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ("PostgresWorkflowBundleImportStore",)
