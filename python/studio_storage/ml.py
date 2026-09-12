"""Durable experiment tracking and model registry persistence for Public v1."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from studio_core import AssetRef, WorkspaceId
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.ml import (
    EvaluationStatus,
    Experiment,
    ExperimentId,
    MLRunId,
    MLRunRecord,
    MetricValue,
    ModelEvaluation,
    ModelId,
    ModelSignature,
    ModelStage,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound, migrate_catalog
from .sqlite import open_database
from .workspaces import WorkspaceNotFound

_ML_SCHEMA_VERSION = 1
_ML_MIGRATIONS = {1: "ml_001.sql"}


class MLConflict(RuntimeError):
    """Raised when immutable ML identity is reused with different content."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            connection.execute(statement)


def migrate_ml(connection: sqlite3.Connection, *, now: Instant | str) -> None:
    now = Instant(now)
    migrate_catalog(connection, now=now)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS ml_schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = connection.execute("SELECT MAX(version) AS version FROM ml_schema_migrations").fetchone()
    current = 0 if row is None or row["version"] is None else int(row["version"])
    if current > _ML_SCHEMA_VERSION:
        raise RuntimeError(f"ML schema {current} is newer than supported {_ML_SCHEMA_VERSION}")
    migrations_dir = Path(__file__).with_name("migrations")
    for version in range(current + 1, _ML_SCHEMA_VERSION + 1):
        script = migrations_dir.joinpath(_ML_MIGRATIONS[version]).read_text(encoding="utf-8")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _execute_script_in_transaction(connection, script)
            connection.execute(
                "INSERT INTO ml_schema_migrations(version,applied_at) VALUES (?,?)",
                (version, now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def ml_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM ml_schema_migrations").fetchone()
    return 0 if row is None or row["version"] is None else int(row["version"])


def _model_from_json(payload: str) -> RegisteredModelVersion:
    value = decode_canonical_json(payload)
    if not isinstance(value, Mapping):
        raise ValueError("registered model payload must be object")
    signature = value.get("signature")
    if not isinstance(signature, Mapping):
        raise ValueError("registered model signature must be object")
    inputs, outputs = signature.get("inputs"), signature.get("outputs")
    if not isinstance(inputs, Mapping) or not isinstance(outputs, Mapping):
        raise ValueError("registered model signature inputs/outputs must be objects")
    required = {"model_id","version","source_run_id","artifact_ref","artifact_digest","framework","signature","stage"}
    if set(value) != required:
        raise ValueError("registered model payload has invalid shape")
    string_fields = [value[k] for k in ("model_id","version","source_run_id","artifact_ref","artifact_digest","framework","stage")]
    if not all(isinstance(item, str) for item in string_fields):
        raise ValueError("registered model fields must be strings")
    return RegisteredModelVersion(
        ModelId(cast(str, value["model_id"])),
        ModelVersion(cast(str, value["version"])),
        MLRunId(cast(str, value["source_run_id"])),
        cast(str, value["artifact_ref"]),
        cast(str, value["artifact_digest"]),
        cast(str, value["framework"]),
        ModelSignature(
            tuple(sorted((cast(str,k), cast(str,v)) for k,v in inputs.items())),
            tuple(sorted((cast(str,k), cast(str,v)) for k,v in outputs.items())),
        ),
        cast(ModelStage, value["stage"]),
    )


def _evaluation_from_json(payload: str) -> ModelEvaluation:
    value = decode_canonical_json(payload)
    required = {"model_id","version","dataset","status","metrics","execution_ref"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("model evaluation payload has invalid shape")
    metrics = value["metrics"]
    if not isinstance(metrics, list):
        raise ValueError("model evaluation metrics must be array")
    parsed: list[MetricValue] = []
    for item in metrics:
        if not isinstance(item, Mapping) or set(item) != {"name","value","step"}:
            raise ValueError("model evaluation metric has invalid shape")
        name, metric_value, step = item["name"], item["value"], item["step"]
        if not isinstance(name,str) or not isinstance(metric_value,(int,float)) or isinstance(metric_value,bool) or not isinstance(step,int) or isinstance(step,bool):
            raise ValueError("model evaluation metric has invalid types")
        parsed.append(MetricValue(name,float(metric_value),step))
    model_id, version, status, execution_ref = value["model_id"],value["version"],value["status"],value["execution_ref"]
    if not all(isinstance(item,str) for item in (model_id,version,status,execution_ref)):
        raise ValueError("model evaluation fields have invalid types")
    return ModelEvaluation(ModelId(cast(str,model_id)),ModelVersion(cast(str,version)),AssetRef.from_payload(value["dataset"]),cast(EvaluationStatus,status),tuple(parsed),cast(str,execution_ref))


class SqliteMLStore:
    """SQLite reference store for immutable training/evaluation provenance."""

    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            migrate_ml(connection, now=migration_now)
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def _require_active_workspace(self, connection: sqlite3.Connection, workspace_id: WorkspaceId) -> None:
        row = connection.execute("SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)).fetchone()
        if row is None: raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None: raise MLConflict("cannot mutate ML state in an archived workspace")

    def _require_asset_ref(self, connection: sqlite3.Connection, workspace_id: WorkspaceId, ref: AssetRef) -> None:
        row = connection.execute("SELECT 1 FROM catalog_asset_revisions WHERE workspace_id=? AND asset_id=? AND version=?", (str(workspace_id),str(ref.asset_id),str(ref.version))).fetchone()
        if row is None: raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")

    def put_experiment(self, workspace_id: WorkspaceId, experiment: Experiment, *, now: Instant | str) -> Experiment:
        now=Instant(now); payload=experiment.to_json(); connection=self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE"); self._require_active_workspace(connection,workspace_id)
            row=connection.execute("SELECT experiment_json FROM ml_experiments WHERE workspace_id=? AND experiment_id=?",(str(workspace_id),str(experiment.id))).fetchone()
            if row is None:
                connection.execute("INSERT INTO ml_experiments(workspace_id,experiment_id,experiment_json,created_at,updated_at) VALUES (?,?,?,?,?)",(str(workspace_id),str(experiment.id),payload,now,now))
            elif row["experiment_json"] != payload:
                connection.execute("UPDATE ml_experiments SET experiment_json=?,updated_at=?,row_version=row_version+1 WHERE workspace_id=? AND experiment_id=?",(payload,now,str(workspace_id),str(experiment.id)))
            connection.execute("COMMIT"); return experiment
        except Exception:
            if connection.in_transaction: connection.execute("ROLLBACK")
            raise
        finally: connection.close()

    def get_experiment(self, workspace_id: WorkspaceId, experiment_id: ExperimentId) -> Experiment | None:
        connection=self._connect()
        try:
            row=connection.execute("SELECT experiment_json FROM ml_experiments WHERE workspace_id=? AND experiment_id=?",(str(workspace_id),str(experiment_id))).fetchone()
            return None if row is None else Experiment.from_json(row["experiment_json"])
        finally: connection.close()

    def record_run(self, workspace_id: WorkspaceId, run: MLRunRecord, *, now: Instant | str) -> MLRunRecord:
        now=Instant(now); payload=run.to_json(); connection=self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE"); self._require_active_workspace(connection,workspace_id)
            experiment=connection.execute("SELECT 1 FROM ml_experiments WHERE workspace_id=? AND experiment_id=?",(str(workspace_id),str(run.experiment_id))).fetchone()
            if experiment is None: raise KeyError(str(run.experiment_id))
            for ref in run.datasets: self._require_asset_ref(connection,workspace_id,ref)
            existing=connection.execute("SELECT run_json FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",(str(workspace_id),str(run.id))).fetchone()
            if existing is not None:
                if existing["run_json"] == payload: connection.execute("COMMIT"); return run
                raise MLConflict(f"ML run id already exists: {run.id}")
            connection.execute("INSERT INTO ml_runs(workspace_id,ml_run_id,experiment_id,run_json,created_at) VALUES (?,?,?,?,?)",(str(workspace_id),str(run.id),str(run.experiment_id),payload,now))
            connection.execute("COMMIT"); return run
        except Exception:
            if connection.in_transaction: connection.execute("ROLLBACK")
            raise
        finally: connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: MLRunId) -> MLRunRecord | None:
        connection=self._connect()
        try:
            row=connection.execute("SELECT run_json FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",(str(workspace_id),str(run_id))).fetchone()
            return None if row is None else MLRunRecord.from_json(row["run_json"])
        finally: connection.close()

    def register_model(self, workspace_id: WorkspaceId, model: RegisteredModelVersion, *, now: Instant | str) -> RegisteredModelVersion:
        now=Instant(now); payload=model.to_json(); connection=self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE"); self._require_active_workspace(connection,workspace_id)
            source=connection.execute("SELECT 1 FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",(str(workspace_id),str(model.source_run_id))).fetchone()
            if source is None: raise KeyError(str(model.source_run_id))
            existing=connection.execute("SELECT model_json FROM model_versions WHERE workspace_id=? AND model_id=? AND version=?",(str(workspace_id),str(model.model_id),str(model.version))).fetchone()
            if existing is not None:
                if existing["model_json"] == payload: connection.execute("COMMIT"); return model
                raise MLConflict(f"model version already exists: {model.model_id}@{model.version}")
            connection.execute("INSERT INTO model_versions(workspace_id,model_id,version,source_ml_run_id,stage,model_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",(str(workspace_id),str(model.model_id),str(model.version),str(model.source_run_id),model.stage,payload,now,now))
            connection.execute("COMMIT"); return model
        except Exception:
            if connection.in_transaction: connection.execute("ROLLBACK")
            raise
        finally: connection.close()

    def get_model(self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion) -> RegisteredModelVersion | None:
        connection=self._connect()
        try:
            row=connection.execute("SELECT model_json FROM model_versions WHERE workspace_id=? AND model_id=? AND version=?",(str(workspace_id),str(model_id),str(version))).fetchone()
            return None if row is None else _model_from_json(row["model_json"])
        finally: connection.close()

    def record_evaluation(self, workspace_id: WorkspaceId, evaluation: ModelEvaluation, *, now: Instant | str) -> ModelEvaluation:
        now=Instant(now); payload=evaluation.to_json(); digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(); connection=self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE"); self._require_active_workspace(connection,workspace_id); self._require_asset_ref(connection,workspace_id,evaluation.dataset)
            model=connection.execute("SELECT 1 FROM model_versions WHERE workspace_id=? AND model_id=? AND version=?",(str(workspace_id),str(evaluation.model_id),str(evaluation.version))).fetchone()
            if model is None: raise KeyError(f"{evaluation.model_id}@{evaluation.version}")
            existing=connection.execute("SELECT evaluation_json FROM model_evaluations WHERE workspace_id=? AND model_id=? AND version=? AND evaluation_digest=?",(str(workspace_id),str(evaluation.model_id),str(evaluation.version),digest)).fetchone()
            if existing is None:
                connection.execute("INSERT INTO model_evaluations(workspace_id,model_id,version,evaluation_digest,evaluation_json,created_at) VALUES (?,?,?,?,?,?)",(str(workspace_id),str(evaluation.model_id),str(evaluation.version),digest,payload,now))
            connection.execute("COMMIT"); return evaluation
        except Exception:
            if connection.in_transaction: connection.execute("ROLLBACK")
            raise
        finally: connection.close()

    def list_evaluations(self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion) -> tuple[ModelEvaluation,...]:
        connection=self._connect()
        try:
            rows=connection.execute("SELECT evaluation_json FROM model_evaluations WHERE workspace_id=? AND model_id=? AND version=? ORDER BY evaluation_digest",(str(workspace_id),str(model_id),str(version))).fetchall()
            return tuple(_evaluation_from_json(row["evaluation_json"]) for row in rows)
        finally: connection.close()
