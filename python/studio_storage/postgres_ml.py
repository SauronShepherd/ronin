"""PostgreSQL adapter for ML experiment, registry and evaluation provenance."""

from __future__ import annotations

import hashlib

from studio_core import AssetRef, WorkspaceId
from studio_core.ml import (
    Experiment,
    ExperimentId,
    MLRunId,
    MLRunRecord,
    ModelEvaluation,
    ModelId,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound
from .ml import MLConflict, _evaluation_from_json, _model_from_json
from .postgres_core import PostgresMetadataStore
from .workspaces import WorkspaceNotFound


class PostgresMLStore(PostgresMetadataStore):
    """Provider-neutral PostgreSQL implementation of the ML registry store."""

    def migrate(self) -> None:
        super().migrate()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_experiments ("
                    "workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,"
                    "experiment_id TEXT NOT NULL, experiment_json TEXT NOT NULL, created_at TEXT NOT NULL,"
                    "updated_at TEXT NOT NULL, PRIMARY KEY(workspace_id, experiment_id))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_runs ("
                    "workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,"
                    "ml_run_id TEXT NOT NULL, experiment_id TEXT NOT NULL, run_json TEXT NOT NULL,"
                    "created_at TEXT NOT NULL, PRIMARY KEY(workspace_id, ml_run_id))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_models ("
                    "workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,"
                    "model_id TEXT NOT NULL, version TEXT NOT NULL, source_ml_run_id TEXT NOT NULL,"
                    "stage TEXT NOT NULL, model_json TEXT NOT NULL, created_at TEXT NOT NULL,"
                    "updated_at TEXT NOT NULL, PRIMARY KEY(workspace_id, model_id, version))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_evaluations ("
                    "workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) ON DELETE CASCADE,"
                    "model_id TEXT NOT NULL, version TEXT NOT NULL, evaluation_digest TEXT NOT NULL,"
                    "evaluation_json TEXT NOT NULL, created_at TEXT NOT NULL,"
                    "PRIMARY KEY(workspace_id, model_id, version, evaluation_digest))"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _active(self, cursor, workspace_id: WorkspaceId) -> None:
        cursor.execute(
            "SELECT archived_at FROM ronin_workspaces WHERE workspace_id=%s",
            (str(workspace_id),),
        )
        row = cursor.fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise MLConflict("cannot mutate ML state in an archived workspace")

    def _asset(self, cursor, workspace_id: WorkspaceId, ref: AssetRef) -> None:
        cursor.execute(
            "SELECT 1 FROM ronin_catalog_revisions WHERE workspace_id=%s AND asset_id=%s AND version=%s",
            (str(workspace_id), str(ref.asset_id), str(ref.version)),
        )
        if cursor.fetchone() is None:
            raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")

    def put_experiment(self, workspace_id: WorkspaceId, experiment: Experiment, *, now: Instant | str) -> Experiment:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._active(cursor, workspace_id)
                cursor.execute(
                    "INSERT INTO ronin_ml_experiments VALUES (%s,%s,%s,%s,%s) "
                    "ON CONFLICT (workspace_id,experiment_id) DO UPDATE SET experiment_json=EXCLUDED.experiment_json,updated_at=EXCLUDED.updated_at",
                    (str(workspace_id), str(experiment.id), experiment.to_json(), str(now), str(now)),
                )
            connection.commit()
            return experiment
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_experiment(self, workspace_id: WorkspaceId, experiment_id: ExperimentId) -> Experiment | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT experiment_json FROM ronin_ml_experiments WHERE workspace_id=%s AND experiment_id=%s", (str(workspace_id), str(experiment_id)))
                row = cursor.fetchone()
            return None if row is None else Experiment.from_json(row["experiment_json"])
        finally:
            connection.close()

    def record_run(self, workspace_id: WorkspaceId, run: MLRunRecord, *, now: Instant | str) -> MLRunRecord:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._active(cursor, workspace_id)
                cursor.execute("SELECT 1 FROM ronin_ml_experiments WHERE workspace_id=%s AND experiment_id=%s", (str(workspace_id), str(run.experiment_id)))
                if cursor.fetchone() is None:
                    raise KeyError(str(run.experiment_id))
                for ref in run.datasets:
                    self._asset(cursor, workspace_id, ref)
                cursor.execute("SELECT run_json FROM ronin_ml_runs WHERE workspace_id=%s AND ml_run_id=%s", (str(workspace_id), str(run.id)))
                existing = cursor.fetchone()
                if existing is not None:
                    if existing["run_json"] == run.to_json():
                        connection.commit()
                        return run
                    raise MLConflict(f"ML run id already exists: {run.id}")
                cursor.execute("INSERT INTO ronin_ml_runs VALUES (%s,%s,%s,%s,%s)", (str(workspace_id), str(run.id), str(run.experiment_id), run.to_json(), str(now)))
            connection.commit()
            return run
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: MLRunId) -> MLRunRecord | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT run_json FROM ronin_ml_runs WHERE workspace_id=%s AND ml_run_id=%s", (str(workspace_id), str(run_id)))
                row = cursor.fetchone()
            return None if row is None else MLRunRecord.from_json(row["run_json"])
        finally:
            connection.close()

    def register_model(self, workspace_id: WorkspaceId, model: RegisteredModelVersion, *, now: Instant | str) -> RegisteredModelVersion:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                self._active(cursor, workspace_id)
                cursor.execute("SELECT 1 FROM ronin_ml_runs WHERE workspace_id=%s AND ml_run_id=%s", (str(workspace_id), str(model.source_run_id)))
                if cursor.fetchone() is None:
                    raise KeyError(str(model.source_run_id))
                cursor.execute("SELECT model_json FROM ronin_ml_models WHERE workspace_id=%s AND model_id=%s AND version=%s", (str(workspace_id), str(model.model_id), str(model.version)))
                existing = cursor.fetchone()
                if existing is not None:
                    if existing["model_json"] == model.to_json():
                        connection.commit()
                        return model
                    raise MLConflict(f"model version already exists: {model.model_id}@{model.version}")
                cursor.execute("INSERT INTO ronin_ml_models VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (str(workspace_id), str(model.model_id), str(model.version), str(model.source_run_id), model.stage, model.to_json(), str(now), str(now)))
            connection.commit()
            return model
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_model(self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion) -> RegisteredModelVersion | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT model_json FROM ronin_ml_models WHERE workspace_id=%s AND model_id=%s AND version=%s", (str(workspace_id), str(model_id), str(version)))
                row = cursor.fetchone()
            return None if row is None else _model_from_json(row["model_json"])
        finally:
            connection.close()

    def get_champion_model(self, workspace_id: WorkspaceId, model_id: ModelId) -> RegisteredModelVersion | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT model_json FROM ronin_ml_models WHERE workspace_id=%s AND model_id=%s AND stage='champion'", (str(workspace_id), str(model_id)))
                row = cursor.fetchone()
            return None if row is None else _model_from_json(row["model_json"])
        finally:
            connection.close()

    def list_models(self, workspace_id: WorkspaceId, model_id: ModelId | None = None) -> tuple[RegisteredModelVersion, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                if model_id is None:
                    cursor.execute("SELECT model_json FROM ronin_ml_models WHERE workspace_id=%s ORDER BY model_id,version", (str(workspace_id),))
                else:
                    cursor.execute("SELECT model_json FROM ronin_ml_models WHERE workspace_id=%s AND model_id=%s ORDER BY version", (str(workspace_id), str(model_id)))
                rows = cursor.fetchall()
            return tuple(_model_from_json(row["model_json"]) for row in rows)
        finally:
            connection.close()

    def record_evaluation(self, workspace_id: WorkspaceId, evaluation: ModelEvaluation, *, now: Instant | str) -> ModelEvaluation:
        connection = self._connect()
        try:
            digest = hashlib.sha256(evaluation.to_json().encode()).hexdigest()
            with connection.cursor() as cursor:
                self._active(cursor, workspace_id)
                self._asset(cursor, workspace_id, evaluation.dataset)
                cursor.execute("SELECT 1 FROM ronin_ml_models WHERE workspace_id=%s AND model_id=%s AND version=%s", (str(workspace_id), str(evaluation.model_id), str(evaluation.version)))
                if cursor.fetchone() is None:
                    raise KeyError(f"{evaluation.model_id}@{evaluation.version}")
                cursor.execute("INSERT INTO ronin_ml_evaluations VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (str(workspace_id), str(evaluation.model_id), str(evaluation.version), digest, evaluation.to_json(), str(now)))
            connection.commit()
            return evaluation
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_evaluations(self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion) -> tuple[ModelEvaluation, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT evaluation_json FROM ronin_ml_evaluations WHERE workspace_id=%s AND model_id=%s AND version=%s ORDER BY evaluation_digest", (str(workspace_id), str(model_id), str(version)))
                rows = cursor.fetchall()
            return tuple(_evaluation_from_json(row["evaluation_json"]) for row in rows)
        finally:
            connection.close()


__all__ = ("PostgresMLStore",)
