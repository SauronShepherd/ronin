"""PostgreSQL persistence for the local ML Studio composition."""

from __future__ import annotations

from studio_core import WorkspaceId
from studio_ml.domain import Lab, PipelineIR
from studio_ml.orchestration import ExecutionSnapshot, ExecutionStore
from studio_ml.ports import MLLabStore
from studio_ml.services import MLLabConflict
from studio_storage.postgres_core import PostgresMetadataStore


class PostgresMLLabStore(PostgresMetadataStore, MLLabStore):
    """Durable PostgreSQL adapter for labs and pipeline definitions."""

    def migrate(self) -> None:
        super().migrate()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_labs "
                    "(workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) "
                    "ON DELETE CASCADE, lab_id TEXT NOT NULL, lab_json TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_id, lab_id))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_pipelines "
                    "(workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) "
                    "ON DELETE CASCADE, lab_id TEXT NOT NULL, pipeline_json TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_id, lab_id))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_executions "
                    "(run_id TEXT PRIMARY KEY, state TEXT NOT NULL, error TEXT, result_json TEXT)"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        payload = lab.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_json FROM ronin_ml_studio_labs WHERE workspace_id=%s AND lab_id=%s",
                    (str(workspace_id), lab.id),
                )
                row = cursor.fetchone()
                if row is not None and row["lab_json"] != payload:
                    raise MLLabConflict(f"lab id already exists: {lab.id}")
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_labs(workspace_id,lab_id,lab_json) "
                    "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (str(workspace_id), lab.id, payload),
                )
            connection.commit()
            return lab
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_json FROM ronin_ml_studio_labs WHERE workspace_id=%s AND lab_id=%s",
                    (str(workspace_id), lab_id),
                )
                row = cursor.fetchone()
            return None if row is None else Lab.from_json(row["lab_json"])
        finally:
            connection.close()

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_json FROM ronin_ml_studio_labs "
                    "WHERE workspace_id=%s ORDER BY lab_id",
                    (str(workspace_id),),
                )
                rows = cursor.fetchall()
            return tuple(Lab.from_json(row["lab_json"]) for row in rows)
        finally:
            connection.close()

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_pipelines(workspace_id,lab_id,pipeline_json) "
                    "VALUES (%s,%s,%s) ON CONFLICT (workspace_id,lab_id) DO UPDATE "
                    "SET pipeline_json=EXCLUDED.pipeline_json",
                    (str(workspace_id), lab_id, pipeline.to_json()),
                )
            connection.commit()
            return pipeline
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pipeline_json FROM ronin_ml_studio_pipelines "
                    "WHERE workspace_id=%s AND lab_id=%s",
                    (str(workspace_id), lab_id),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            raw = row["pipeline_json"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                raise ValueError("stored ML pipeline must be JSON text")
            return PipelineIR.from_json(raw)
        finally:
            connection.close()


class PostgresExecutionStore(PostgresMetadataStore, ExecutionStore):
    """Durable execution lifecycle store for ML Studio."""

    def put(self, snapshot: ExecutionSnapshot) -> None:
        payload = (
            snapshot.result.to_payload() if snapshot.result is not None else snapshot.result_payload
        )
        connection = self._connect()
        try:
            import json

            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_executions(run_id,state,error,result_json) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (run_id) DO UPDATE SET "
                    "state=EXCLUDED.state,error=EXCLUDED.error,result_json=EXCLUDED.result_json",
                    (
                        snapshot.run_id,
                        snapshot.state,
                        snapshot.error,
                        None if payload is None else json.dumps(payload, sort_keys=True),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, run_id: str) -> ExecutionSnapshot | None:
        connection = self._connect()
        try:
            import json

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT run_id,state,error,result_json FROM ronin_ml_studio_executions "
                    "WHERE run_id=%s",
                    (run_id,),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            return ExecutionSnapshot(
                row["run_id"],
                row["state"],
                error=row["error"],
                result_payload=None
                if row["result_json"] is None
                else json.loads(row["result_json"]),
            )
        finally:
            connection.close()


__all__ = ("PostgresExecutionStore", "PostgresMLLabStore")
