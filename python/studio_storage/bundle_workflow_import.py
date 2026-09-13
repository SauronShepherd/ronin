"""Atomic SQLite commit boundary for native workflow/schedule Bundle imports."""

from __future__ import annotations

from pathlib import Path

from studio_core import Schedule, WorkflowDefinition, WorkspaceId
from studio_orchestrator import Instant

from .bundle_workflow_import_port import (
    WorkflowBundleImportCommit,
    WorkflowBundleImportConflict,
)
from .scheduler import SqliteSchedulerStore, migrate_scheduler
from .sqlite import open_database
from .workspaces import SqliteWorkspaceStore


class SqliteWorkflowBundleImportStore(SqliteWorkspaceStore, SqliteSchedulerStore):
    """SQLite adapter that atomically commits portable scheduler definitions only."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        SqliteWorkspaceStore.__init__(self, path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler(connection, now=migration_now)
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
        workflow_ids = [item.id for item in workflows]
        schedule_ids = [item.id for item in schedules]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("workflow import definitions must have unique ids")
        if len(schedule_ids) != len(set(schedule_ids)):
            raise ValueError("workflow import schedules must have unique ids")

        imported_workflow_ids = set(workflow_ids)
        for schedule in schedules:
            if schedule.workflow_id not in imported_workflow_ids:
                raise ValueError(
                    "workflow import schedule must reference an imported workflow definition"
                )

        current = Instant(now)
        database = self._connect()
        try:
            database.execute("BEGIN IMMEDIATE")
            workspace = database.execute(
                "SELECT archived_at FROM workspaces WHERE workspace_id=?",
                (str(workspace_id),),
            ).fetchone()
            if workspace is None:
                raise WorkflowBundleImportConflict("target workspace does not exist")
            if workspace["archived_at"] is not None:
                raise WorkflowBundleImportConflict("target workspace is archived")

            workflows_created = 0
            for workflow in sorted(workflows, key=lambda item: item.id.value):
                payload = workflow.to_json()
                existing = database.execute(
                    "SELECT definition_json FROM workflows "
                    "WHERE workspace_id=? AND workflow_id=?",
                    (str(workspace_id), str(workflow.id)),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO workflows("
                        "workspace_id,workflow_id,definition_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(workflow.id),
                            payload,
                            current,
                            current,
                        ),
                    )
                    workflows_created += 1
                elif existing["definition_json"] != payload:
                    raise WorkflowBundleImportConflict(
                        f"workflow id already exists with different portable definition: {workflow.id}"
                    )

            schedules_created = 0
            for schedule in sorted(schedules, key=lambda item: item.id.value):
                workflow = database.execute(
                    "SELECT 1 FROM workflows WHERE workspace_id=? AND workflow_id=?",
                    (str(workspace_id), str(schedule.workflow_id)),
                ).fetchone()
                if workflow is None:
                    raise WorkflowBundleImportConflict(
                        f"schedule references missing workflow: {schedule.workflow_id}"
                    )
                payload = schedule.to_json()
                existing = database.execute(
                    "SELECT schedule_json FROM schedules "
                    "WHERE workspace_id=? AND schedule_id=?",
                    (str(workspace_id), str(schedule.id)),
                ).fetchone()
                if existing is None:
                    database.execute(
                        "INSERT INTO schedules("
                        "workspace_id,schedule_id,workflow_id,schedule_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(schedule.id),
                            str(schedule.workflow_id),
                            payload,
                            current,
                            current,
                        ),
                    )
                    schedules_created += 1
                elif existing["schedule_json"] != payload:
                    raise WorkflowBundleImportConflict(
                        f"schedule id already exists with different portable definition: {schedule.id}"
                    )

            database.execute("COMMIT")
            return WorkflowBundleImportCommit(workflows_created, schedules_created)
        except Exception:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
        finally:
            database.close()


__all__ = ("SqliteWorkflowBundleImportStore",)
