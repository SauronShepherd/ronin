"""Scheduler controller persistence over deployment bindings and execution outbox."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import EnvironmentDefinition, WorkflowId, WorkspaceId
from studio_core.scheduler_deployment import WorkflowDeploymentBinding
from studio_orchestrator import Instant

from .environments import EnvironmentConflict, migrate_environments
from .scheduler_execution import (
    SchedulerExecutionLinkStore,
    migrate_scheduler_execution,
)
from .sqlite import open_database
from .workspaces import WorkspaceNotFound

_CONTROLLER_SCHEMA_VERSION = 1
_CONTROLLER_MIGRATIONS = {1: "scheduler_controller_001.sql"}


class WorkflowDeploymentConflict(RuntimeError):
    """Raised when a workflow deployment is invalid for current durable state."""


class WorkflowDeploymentNotFound(KeyError):
    """Raised when a workflow has no deployment binding."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_scheduler_controller(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_scheduler_execution(connection, now=now)
    migrate_environments(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS scheduler_controller_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_controller_schema_migrations"
    ).fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _CONTROLLER_SCHEMA_VERSION:
        raise RuntimeError(
            f"scheduler controller schema {current} is newer than supported "
            f"{_CONTROLLER_SCHEMA_VERSION}"
        )
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _CONTROLLER_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_CONTROLLER_MIGRATIONS[version]).read_text(
            encoding="utf-8"
        )
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO scheduler_controller_schema_migrations(version,applied_at) "
                "VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def scheduler_controller_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT MAX(version) AS version FROM scheduler_controller_schema_migrations"
    ).fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


class SchedulerControllerStore(SchedulerExecutionLinkStore):
    """Reference SQLite store for deployable scheduler-controller state."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        super().__init__(path, migration_now=migration_now)
        connection = open_database(path)
        try:
            migrate_scheduler_controller(connection, now=migration_now)
        finally:
            connection.close()

    @staticmethod
    def _require_active_workspace(
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?",
            (str(workspace_id),),
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise WorkflowDeploymentConflict(
                "cannot mutate workflow deployment in an archived workspace"
            )

    def put_workflow_deployment(
        self,
        workspace_id: WorkspaceId,
        binding: WorkflowDeploymentBinding,
        *,
        now: Instant | str,
    ) -> WorkflowDeploymentBinding:
        current = Instant(now)
        payload = binding.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            workflow = connection.execute(
                "SELECT 1 FROM workflows WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(binding.workflow_id)),
            ).fetchone()
            if workflow is None:
                raise WorkflowDeploymentConflict("workflow does not exist in workspace")
            project = connection.execute(
                "SELECT 1 FROM workspace_projects WHERE workspace_id=? AND project_id=?",
                (str(workspace_id), str(binding.project_id)),
            ).fetchone()
            if project is None:
                raise WorkflowDeploymentConflict("project is not registered in workspace")
            if binding.environment_id is not None:
                environment = connection.execute(
                    "SELECT definition_json FROM environments "
                    "WHERE workspace_id=? AND environment_id=?",
                    (str(workspace_id), str(binding.environment_id)),
                ).fetchone()
                if environment is None:
                    raise WorkflowDeploymentConflict("environment does not exist in workspace")
                definition = EnvironmentDefinition.from_json(environment["definition_json"])
                if definition.disabled:
                    raise EnvironmentConflict("cannot deploy workflow to a disabled environment")

            existing = connection.execute(
                "SELECT binding_json FROM workflow_deployments "
                "WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(binding.workflow_id)),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO workflow_deployments("
                    "workspace_id,workflow_id,project_id,environment_id,binding_json,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(binding.workflow_id),
                        str(binding.project_id),
                        None if binding.environment_id is None else str(binding.environment_id),
                        payload,
                        current,
                        current,
                    ),
                )
            elif existing["binding_json"] != payload:
                connection.execute(
                    "UPDATE workflow_deployments SET project_id=?,environment_id=?,"
                    "binding_json=?,updated_at=?,row_version=row_version+1 "
                    "WHERE workspace_id=? AND workflow_id=?",
                    (
                        str(binding.project_id),
                        None if binding.environment_id is None else str(binding.environment_id),
                        payload,
                        current,
                        str(workspace_id),
                        str(binding.workflow_id),
                    ),
                )
            connection.execute("COMMIT")
            return binding
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_workflow_deployment(
        self,
        workspace_id: WorkspaceId,
        workflow_id: WorkflowId,
    ) -> WorkflowDeploymentBinding | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT binding_json FROM workflow_deployments "
                "WHERE workspace_id=? AND workflow_id=?",
                (str(workspace_id), str(workflow_id)),
            ).fetchone()
            return None if row is None else WorkflowDeploymentBinding.from_json(
                row["binding_json"]
            )
        finally:
            connection.close()

    def get_runnable_workflow_deployment(
        self,
        workspace_id: WorkspaceId,
        workflow_id: WorkflowId,
    ) -> WorkflowDeploymentBinding | None:
        """Return a deployment only while its project/environment remain runnable."""

        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT d.binding_json,e.definition_json AS environment_json "
                "FROM workflow_deployments d "
                "LEFT JOIN environments e ON e.workspace_id=d.workspace_id "
                "AND e.environment_id=d.environment_id "
                "JOIN workspace_projects p ON p.workspace_id=d.workspace_id "
                "AND p.project_id=d.project_id "
                "WHERE d.workspace_id=? AND d.workflow_id=?",
                (str(workspace_id), str(workflow_id)),
            ).fetchone()
            if row is None:
                return None
            binding = WorkflowDeploymentBinding.from_json(row["binding_json"])
            if binding.environment_id is not None:
                if row["environment_json"] is None:
                    return None
                environment = EnvironmentDefinition.from_json(row["environment_json"])
                if environment.disabled:
                    return None
            return binding
        finally:
            connection.close()


__all__ = (
    "SchedulerControllerStore",
    "WorkflowDeploymentConflict",
    "WorkflowDeploymentNotFound",
    "WorkspaceId",
    "migrate_scheduler_controller",
    "scheduler_controller_schema_version",
)
