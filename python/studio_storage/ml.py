"""Durable experiment tracking and model registry persistence for Public v1."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

from studio_core import AssetRef, WorkspaceId
from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.ml import (
    EvaluationStatus,
    Experiment,
    ExperimentId,
    MetricValue,
    MLRunId,
    MLRunRecord,
    ModelDeployment,
    ModelEvaluation,
    ModelId,
    ModelSignature,
    ModelStage,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import Instant

from .catalog import CatalogAssetNotFound, migrate_catalog
from .sqlite import execute_migration_script, open_database
from .workspaces import WorkspaceNotFound

_ML_SCHEMA_VERSION = 2
_ML_MIGRATIONS = {1: "ml_001.sql", 2: "ml_002.sql"}


class MLConflict(RuntimeError):
    """Raised when immutable ML identity is reused with different content."""


def _execute_script_in_transaction(connection: sqlite3.Connection, script: str) -> None:
    execute_migration_script(connection, script)


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
    required = {
        "model_id",
        "version",
        "source_run_id",
        "artifact_ref",
        "artifact_digest",
        "framework",
        "signature",
        "stage",
    }
    if set(value) != required:
        raise ValueError("registered model payload has invalid shape")
    string_fields = [
        value[k]
        for k in (
            "model_id",
            "version",
            "source_run_id",
            "artifact_ref",
            "artifact_digest",
            "framework",
            "stage",
        )
    ]
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
            tuple(sorted((cast(str, k), cast(str, v)) for k, v in inputs.items())),
            tuple(sorted((cast(str, k), cast(str, v)) for k, v in outputs.items())),
        ),
        cast(ModelStage, value["stage"]),
    )


def _evaluation_from_json(payload: str) -> ModelEvaluation:
    value = decode_canonical_json(payload)
    required = {"model_id", "version", "dataset", "status", "metrics", "execution_ref"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("model evaluation payload has invalid shape")
    metrics = value["metrics"]
    if not isinstance(metrics, list):
        raise ValueError("model evaluation metrics must be array")
    parsed: list[MetricValue] = []
    for item in metrics:
        if not isinstance(item, Mapping) or set(item) != {"name", "value", "step"}:
            raise ValueError("model evaluation metric has invalid shape")
        name, metric_value, step = item["name"], item["value"], item["step"]
        if (
            not isinstance(name, str)
            or not isinstance(metric_value, (int, float))
            or isinstance(metric_value, bool)
            or not isinstance(step, int)
            or isinstance(step, bool)
        ):
            raise ValueError("model evaluation metric has invalid types")
        parsed.append(MetricValue(name, float(metric_value), step))
    model_id, version, status, execution_ref = (
        value["model_id"],
        value["version"],
        value["status"],
        value["execution_ref"],
    )
    if not all(isinstance(item, str) for item in (model_id, version, status, execution_ref)):
        raise ValueError("model evaluation fields have invalid types")
    return ModelEvaluation(
        ModelId(cast(str, model_id)),
        ModelVersion(cast(str, version)),
        AssetRef.from_payload(value["dataset"]),
        cast(EvaluationStatus, status),
        tuple(parsed),
        cast(str, execution_ref),
    )


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
        return cast(sqlite3.Connection, open_database(self._path))

    def _require_active_workspace(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId
    ) -> None:
        row = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if row is None:
            raise WorkspaceNotFound(str(workspace_id))
        if row["archived_at"] is not None:
            raise MLConflict("cannot mutate ML state in an archived workspace")

    def _require_asset_ref(
        self, connection: sqlite3.Connection, workspace_id: WorkspaceId, ref: AssetRef
    ) -> None:
        row = connection.execute(
            "SELECT 1 FROM catalog_asset_revisions "
            "WHERE workspace_id=? AND asset_id=? AND version=?",
            (str(workspace_id), str(ref.asset_id), str(ref.version)),
        ).fetchone()
        if row is None:
            raise CatalogAssetNotFound(f"{ref.asset_id}@{ref.version}")

    def commit_registry_bundle_import(
        self,
        workspace_id: WorkspaceId,
        *,
        experiments: tuple[Experiment, ...],
        runs: tuple[MLRunRecord, ...],
        models: tuple[RegisteredModelVersion, ...],
        evaluations: tuple[ModelEvaluation, ...],
        feature_definitions: tuple[object, ...] = (),
        feature_store: object | None = None,
        now: Instant | str,
    ) -> None:
        """Atomically publish one ML registry Bundle into this SQLite database.

        Feature definitions use the transaction-aware adapter method so the ML
        registry and feature records share this connection and commit boundary.
        """

        now = Instant(now)
        self.validate_registry_bundle_import(
            feature_definitions=feature_definitions,
            feature_store=feature_store,
        )
        feature_writer = getattr(feature_store, "put_feature_definition_in_transaction", None)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)

            for experiment in experiments:
                payload = experiment.to_json()
                existing = connection.execute(
                    "SELECT experiment_json FROM ml_experiments "
                    "WHERE workspace_id=? AND experiment_id=?",
                    (str(workspace_id), str(experiment.id)),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO ml_experiments(workspace_id,experiment_id,experiment_json,"
                        "created_at,updated_at) VALUES (?,?,?,?,?)",
                        (str(workspace_id), str(experiment.id), payload, now, now),
                    )
                elif existing["experiment_json"] != payload:
                    raise ValueError(
                        f"experiment id already exists with a different definition: {experiment.id}"
                    )

            if feature_definitions:
                if not callable(feature_writer):
                    raise ValueError("atomic ML Bundle feature store lost its transaction writer")
                for definition in feature_definitions:
                    dataset = getattr(definition, "dataset", None)
                    if not isinstance(dataset, AssetRef):
                        raise ValueError("ML Bundle feature definition has an invalid dataset ref")
                    self._require_asset_ref(connection, workspace_id, dataset)
                    feature_writer(connection, workspace_id, definition)

            for run in runs:
                payload = run.to_json()
                if (
                    connection.execute(
                        "SELECT 1 FROM ml_experiments WHERE workspace_id=? AND experiment_id=?",
                        (str(workspace_id), str(run.experiment_id)),
                    ).fetchone()
                    is None
                ):
                    raise KeyError(str(run.experiment_id))
                for ref in run.datasets:
                    self._require_asset_ref(connection, workspace_id, ref)
                existing = connection.execute(
                    "SELECT run_json FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",
                    (str(workspace_id), str(run.id)),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO ml_runs(workspace_id,ml_run_id,experiment_id,run_json,"
                        "created_at) VALUES (?,?,?,?,?)",
                        (str(workspace_id), str(run.id), str(run.experiment_id), payload, now),
                    )
                elif existing["run_json"] != payload:
                    raise MLConflict(f"ML run id already exists: {run.id}")

            for model in models:
                payload = model.to_json()
                if (
                    connection.execute(
                        "SELECT 1 FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",
                        (str(workspace_id), str(model.source_run_id)),
                    ).fetchone()
                    is None
                ):
                    raise KeyError(str(model.source_run_id))
                if model.stage == "champion":
                    champion = connection.execute(
                        "SELECT version FROM model_versions WHERE workspace_id=? "
                        "AND model_id=? AND stage='champion'",
                        (str(workspace_id), str(model.model_id)),
                    ).fetchone()
                    if champion is not None and champion["version"] != str(model.version):
                        raise MLConflict(
                            f"model already has a different champion version: {model.model_id}"
                        )
                existing = connection.execute(
                    "SELECT model_json FROM model_versions "
                    "WHERE workspace_id=? AND model_id=? AND version=?",
                    (str(workspace_id), str(model.model_id), str(model.version)),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO model_versions(workspace_id,model_id,version,source_ml_run_id,"
                        "stage,model_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            str(workspace_id),
                            str(model.model_id),
                            str(model.version),
                            str(model.source_run_id),
                            model.stage,
                            payload,
                            now,
                            now,
                        ),
                    )
                elif existing["model_json"] != payload:
                    raise MLConflict(
                        f"model version already exists: {model.model_id}@{model.version}"
                    )

            for evaluation in evaluations:
                self._require_asset_ref(connection, workspace_id, evaluation.dataset)
                key = (str(workspace_id), str(evaluation.model_id), str(evaluation.version))
                if (
                    connection.execute(
                        "SELECT 1 FROM model_versions WHERE workspace_id=? AND model_id=? "
                        "AND version=?",
                        key,
                    ).fetchone()
                    is None
                ):
                    raise KeyError(f"{evaluation.model_id}@{evaluation.version}")
                payload = evaluation.to_json()
                digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                existing = connection.execute(
                    "SELECT evaluation_json FROM model_evaluations WHERE workspace_id=? "
                    "AND model_id=? AND version=? AND evaluation_digest=?",
                    (*key, digest),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO model_evaluations(workspace_id,model_id,version,"
                        "evaluation_digest,evaluation_json,created_at) VALUES (?,?,?,?,?,?)",
                        (*key, digest, payload, now),
                    )
                elif existing["evaluation_json"] != payload:
                    raise MLConflict(
                        f"model evaluation digest collision: {evaluation.model_id}@{evaluation.version}"
                    )

            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def validate_registry_bundle_import(
        self,
        *,
        feature_definitions: tuple[object, ...],
        feature_store: object | None,
    ) -> None:
        """Check feature-store transaction compatibility before external writes."""

        feature_writer = None
        if feature_definitions:
            feature_writer = getattr(feature_store, "put_feature_definition_in_transaction", None)
            feature_path = getattr(feature_store, "database_path", None)
            if not callable(feature_writer) or feature_path is None:
                raise ValueError(
                    "atomic ML Bundle feature import requires a transaction-aware feature store"
                )
            if Path(feature_path).resolve() != self._path.resolve():
                raise ValueError("atomic ML Bundle stores must share one SQLite database")

    def put_experiment(
        self, workspace_id: WorkspaceId, experiment: Experiment, *, now: Instant | str
    ) -> Experiment:
        now = Instant(now)
        payload = experiment.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            row = connection.execute(
                "SELECT experiment_json FROM ml_experiments "
                "WHERE workspace_id=? AND experiment_id=?",
                (str(workspace_id), str(experiment.id)),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO ml_experiments("
                    "workspace_id,experiment_id,experiment_json,created_at,updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (str(workspace_id), str(experiment.id), payload, now, now),
                )
            elif row["experiment_json"] != payload:
                raise ValueError("experiment id already exists with a different definition")
            connection.execute("COMMIT")
            return experiment
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_experiment(
        self, workspace_id: WorkspaceId, experiment_id: ExperimentId
    ) -> Experiment | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT experiment_json FROM ml_experiments "
                "WHERE workspace_id=? AND experiment_id=?",
                (str(workspace_id), str(experiment_id)),
            ).fetchone()
            return None if row is None else Experiment.from_json(row["experiment_json"])
        finally:
            connection.close()

    def list_experiments(self, workspace_id: WorkspaceId) -> tuple[Experiment, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT experiment_json FROM ml_experiments WHERE workspace_id=? "
                "ORDER BY experiment_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(Experiment.from_json(row["experiment_json"]) for row in rows)
        finally:
            connection.close()

    def record_run(
        self, workspace_id: WorkspaceId, run: MLRunRecord, *, now: Instant | str
    ) -> MLRunRecord:
        now = Instant(now)
        payload = run.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            experiment = connection.execute(
                "SELECT 1 FROM ml_experiments WHERE workspace_id=? AND experiment_id=?",
                (str(workspace_id), str(run.experiment_id)),
            ).fetchone()
            if experiment is None:
                raise KeyError(str(run.experiment_id))
            for ref in run.datasets:
                self._require_asset_ref(connection, workspace_id, ref)
            existing = connection.execute(
                "SELECT run_json FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",
                (str(workspace_id), str(run.id)),
            ).fetchone()
            if existing is not None:
                if existing["run_json"] == payload:
                    connection.execute("COMMIT")
                    return run
                raise MLConflict(f"ML run id already exists: {run.id}")
            connection.execute(
                "INSERT INTO ml_runs("
                "workspace_id,ml_run_id,experiment_id,run_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (str(workspace_id), str(run.id), str(run.experiment_id), payload, now),
            )
            connection.execute("COMMIT")
            return run
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_run(self, workspace_id: WorkspaceId, run_id: MLRunId) -> MLRunRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT run_json FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",
                (str(workspace_id), str(run_id)),
            ).fetchone()
            return None if row is None else MLRunRecord.from_json(row["run_json"])
        finally:
            connection.close()

    def list_runs(
        self, workspace_id: WorkspaceId, *, limit: int | None = None
    ) -> tuple[MLRunRecord, ...]:
        if limit is not None and limit < 1:
            raise ValueError("ML run list limit must be positive")
        connection = self._connect()
        try:
            sql = "SELECT run_json FROM ml_runs WHERE workspace_id=? ORDER BY ml_run_id"
            if limit is not None:
                sql += " LIMIT ?"
                rows = connection.execute(sql, (str(workspace_id), limit + 1)).fetchall()
                if len(rows) > limit:
                    raise ValueError("ML run inventory exceeded its bound")
            else:
                rows = connection.execute(sql, (str(workspace_id),)).fetchall()
            return tuple(MLRunRecord.from_json(row["run_json"]) for row in rows)
        finally:
            connection.close()

    def register_model(
        self, workspace_id: WorkspaceId, model: RegisteredModelVersion, *, now: Instant | str
    ) -> RegisteredModelVersion:
        now = Instant(now)
        payload = model.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            source = connection.execute(
                "SELECT 1 FROM ml_runs WHERE workspace_id=? AND ml_run_id=?",
                (str(workspace_id), str(model.source_run_id)),
            ).fetchone()
            if source is None:
                raise KeyError(str(model.source_run_id))
            existing = connection.execute(
                "SELECT model_json FROM model_versions "
                "WHERE workspace_id=? AND model_id=? AND version=?",
                (str(workspace_id), str(model.model_id), str(model.version)),
            ).fetchone()
            if existing is not None:
                if existing["model_json"] == payload:
                    connection.execute("COMMIT")
                    return model
                raise MLConflict(f"model version already exists: {model.model_id}@{model.version}")
            connection.execute(
                "INSERT INTO model_versions("
                "workspace_id,model_id,version,source_ml_run_id,stage,model_json,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(model.model_id),
                    str(model.version),
                    str(model.source_run_id),
                    model.stage,
                    payload,
                    now,
                    now,
                ),
            )
            connection.execute("COMMIT")
            return model
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_model(
        self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion
    ) -> RegisteredModelVersion | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT model_json FROM model_versions "
                "WHERE workspace_id=? AND model_id=? AND version=?",
                (str(workspace_id), str(model_id), str(version)),
            ).fetchone()
            return None if row is None else _model_from_json(row["model_json"])
        finally:
            connection.close()

    def get_champion_model(
        self, workspace_id: WorkspaceId, model_id: ModelId
    ) -> RegisteredModelVersion | None:
        """Resolve the promoted version for a model identity, if one exists."""

        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT model_json FROM model_versions "
                "WHERE workspace_id=? AND model_id=? AND stage='champion'",
                (str(workspace_id), str(model_id)),
            ).fetchone()
            return None if row is None else _model_from_json(row["model_json"])
        finally:
            connection.close()

    def list_models(
        self,
        workspace_id: WorkspaceId,
        model_id: ModelId | None = None,
        *,
        limit: int | None = None,
    ) -> tuple[RegisteredModelVersion, ...]:
        """List registered versions deterministically within one workspace."""

        if limit is not None and limit < 1:
            raise ValueError("model list limit must be positive")
        connection = self._connect()
        try:
            if model_id is None:
                sql = (
                    "SELECT model_json FROM model_versions WHERE workspace_id=? "
                    "ORDER BY model_id, version"
                )
                params: tuple[str, ...] = (str(workspace_id),)
            else:
                sql = (
                    "SELECT model_json FROM model_versions WHERE workspace_id=? AND model_id=? "
                    "ORDER BY version"
                )
                params = (str(workspace_id), str(model_id))
            if limit is not None:
                sql += " LIMIT ?"
                rows = connection.execute(sql, (*params, limit + 1)).fetchall()
                if len(rows) > limit:
                    raise ValueError("registered model inventory exceeded its bound")
            else:
                rows = connection.execute(sql, params).fetchall()
            return tuple(_model_from_json(row["model_json"]) for row in rows)
        finally:
            connection.close()

    def promote_model(
        self,
        workspace_id: WorkspaceId,
        model_id: ModelId,
        version: ModelVersion,
        *,
        now: Instant | str,
    ) -> RegisteredModelVersion:
        """Atomically make one version the champion and archive its predecessor."""

        now = Instant(now)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            target_row = connection.execute(
                "SELECT model_json FROM model_versions "
                "WHERE workspace_id=? AND model_id=? AND version=?",
                (str(workspace_id), str(model_id), str(version)),
            ).fetchone()
            if target_row is None:
                raise KeyError(f"{model_id}@{version}")
            target = _model_from_json(target_row["model_json"])
            evaluations = connection.execute(
                "SELECT evaluation_json FROM model_evaluations "
                "WHERE workspace_id=? AND model_id=? AND version=?",
                (str(workspace_id), str(model_id), str(version)),
            ).fetchall()
            if not any(
                _evaluation_from_json(row["evaluation_json"]).status == "passed"
                for row in evaluations
            ):
                raise MLConflict(f"model version has no passed evaluation: {model_id}@{version}")
            promoted = replace(target, stage="champion")
            rows = connection.execute(
                "SELECT version, model_json FROM model_versions "
                "WHERE workspace_id=? AND model_id=? AND stage='champion'",
                (str(workspace_id), str(model_id)),
            ).fetchall()
            for row in rows:
                current = _model_from_json(row["model_json"])
                archived = replace(current, stage="archived")
                connection.execute(
                    "UPDATE model_versions SET stage=?, model_json=?, updated_at=? "
                    "WHERE workspace_id=? AND model_id=? AND version=?",
                    (
                        archived.stage,
                        archived.to_json(),
                        now,
                        str(workspace_id),
                        str(model_id),
                        str(current.version),
                    ),
                )
            connection.execute(
                "UPDATE model_versions SET stage=?, model_json=?, updated_at=? "
                "WHERE workspace_id=? AND model_id=? AND version=?",
                (
                    promoted.stage,
                    promoted.to_json(),
                    now,
                    str(workspace_id),
                    str(model_id),
                    str(version),
                ),
            )
            connection.execute("COMMIT")
            return promoted
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def record_evaluation(
        self, workspace_id: WorkspaceId, evaluation: ModelEvaluation, *, now: Instant | str
    ) -> ModelEvaluation:
        now = Instant(now)
        payload = evaluation.to_json()
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            self._require_asset_ref(connection, workspace_id, evaluation.dataset)
            model = connection.execute(
                "SELECT 1 FROM model_versions WHERE workspace_id=? AND model_id=? AND version=?",
                (str(workspace_id), str(evaluation.model_id), str(evaluation.version)),
            ).fetchone()
            if model is None:
                raise KeyError(f"{evaluation.model_id}@{evaluation.version}")
            existing = connection.execute(
                "SELECT evaluation_json FROM model_evaluations "
                "WHERE workspace_id=? AND model_id=? AND version=? AND evaluation_digest=?",
                (str(workspace_id), str(evaluation.model_id), str(evaluation.version), digest),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO model_evaluations("
                    "workspace_id,model_id,version,evaluation_digest,evaluation_json,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        str(workspace_id),
                        str(evaluation.model_id),
                        str(evaluation.version),
                        digest,
                        payload,
                        now,
                    ),
                )
            connection.execute("COMMIT")
            return evaluation
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def list_evaluations(
        self, workspace_id: WorkspaceId, model_id: ModelId, version: ModelVersion
    ) -> tuple[ModelEvaluation, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT evaluation_json FROM model_evaluations "
                "WHERE workspace_id=? AND model_id=? AND version=? "
                "ORDER BY evaluation_digest",
                (str(workspace_id), str(model_id), str(version)),
            ).fetchall()
            return tuple(_evaluation_from_json(row["evaluation_json"]) for row in rows)
        finally:
            connection.close()

    def put_deployment(
        self, workspace_id: WorkspaceId, deployment: ModelDeployment, *, now: Instant | str
    ) -> ModelDeployment:
        now = Instant(now)
        payload = deployment.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            model_row = connection.execute(
                "SELECT model_json FROM model_versions WHERE workspace_id=? AND model_id=? AND version=?",
                (str(workspace_id), str(deployment.model_id), str(deployment.version)),
            ).fetchone()
            if model_row is None:
                raise KeyError(f"{deployment.model_id}@{deployment.version}")
            model = _model_from_json(model_row["model_json"])
            if (
                model.artifact_ref != deployment.artifact_ref
                or model.artifact_digest != deployment.artifact_digest
            ):
                raise MLConflict("deployment artifact is not the registered model artifact")
            existing = connection.execute(
                "SELECT deployment_json FROM model_deployments WHERE workspace_id=? AND deployment_id=?",
                (str(workspace_id), deployment.deployment_id),
            ).fetchone()
            if existing is not None:
                if existing["deployment_json"] == payload:
                    connection.execute("COMMIT")
                    return deployment
                raise MLConflict(f"deployment id already exists: {deployment.deployment_id}")
            connection.execute(
                "INSERT INTO model_deployments(workspace_id,deployment_id,deployment_json,created_at,updated_at) VALUES (?,?,?,?,?)",
                (str(workspace_id), deployment.deployment_id, payload, now, now),
            )
            connection.execute("COMMIT")
            return deployment
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_deployment(
        self, workspace_id: WorkspaceId, deployment_id: str
    ) -> ModelDeployment | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT deployment_json FROM model_deployments WHERE workspace_id=? AND deployment_id=?",
                (str(workspace_id), deployment_id),
            ).fetchone()
            return None if row is None else ModelDeployment.from_json(row["deployment_json"])
        finally:
            connection.close()

    def list_deployments(self, workspace_id: WorkspaceId) -> tuple[ModelDeployment, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT deployment_json FROM model_deployments WHERE workspace_id=? ORDER BY deployment_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(ModelDeployment.from_json(row["deployment_json"]) for row in rows)
        finally:
            connection.close()

    def update_deployment(
        self, workspace_id: WorkspaceId, deployment: ModelDeployment, *, now: Instant | str
    ) -> ModelDeployment:
        now = Instant(now)
        payload = deployment.to_json()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_workspace(connection, workspace_id)
            existing = connection.execute(
                "SELECT deployment_json FROM model_deployments WHERE workspace_id=? AND deployment_id=?",
                (str(workspace_id), deployment.deployment_id),
            ).fetchone()
            if existing is None:
                raise KeyError(deployment.deployment_id)
            current = ModelDeployment.from_json(existing["deployment_json"])
            if (
                current.model_id != deployment.model_id
                or current.version != deployment.version
                or current.artifact_ref != deployment.artifact_ref
                or current.artifact_digest != deployment.artifact_digest
                or deployment.revision < current.revision
            ):
                raise MLConflict("deployment identity is immutable")
            connection.execute(
                "UPDATE model_deployments SET deployment_json=?,updated_at=? WHERE workspace_id=? AND deployment_id=?",
                (payload, now, str(workspace_id), deployment.deployment_id),
            )
            connection.execute("COMMIT")
            return deployment
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
