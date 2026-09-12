from __future__ import annotations

from pathlib import Path

import pytest

from studio_core import AssetId, AssetRef, AssetRevision, AssetVersion, CatalogAsset, Workspace, WorkspaceId
from studio_core.ml import (
    Experiment,
    ExperimentId,
    MLRunId,
    MLRunRecord,
    MetricValue,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.ml import MLConflict, SqliteMLStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-12T00:00:00.000000Z")
_WS = WorkspaceId("ws-1")
_DATA = AssetRef(AssetId("dataset-1"), AssetVersion("v1"))


def _stores(path: Path) -> tuple[SqliteMLStore, SqliteCatalogStore]:
    workspaces = SqliteWorkspaceStore(path, migration_now=_NOW)
    workspaces.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    catalog = SqliteCatalogStore(path, migration_now=_NOW)
    catalog.create_asset(_WS, CatalogAsset(AssetId("dataset-1"), "dataset", "training"), now=_NOW)
    catalog.put_revision(_WS, AssetRevision(_DATA, content_digest="sha256:data"), now=_NOW)
    return SqliteMLStore(path, migration_now=_NOW), catalog


def _run() -> MLRunRecord:
    return MLRunRecord(
        id=MLRunId("run-1"),
        experiment_id=ExperimentId("exp-1"),
        execution_ref="job-1/run-1/attempt-1",
        source_revision="git:abc123",
        datasets=(_DATA,),
        parameters=(("max_depth", "4"),),
        metrics=(MetricValue("accuracy", 0.9),),
        artifact_refs=("artifact://model-1",),
    )


def test_training_run_and_model_registry_preserve_provenance(tmp_path: Path) -> None:
    store, _catalog = _stores(tmp_path / "ronin.sqlite3")
    experiment = Experiment(ExperimentId("exp-1"), "Baseline")
    store.put_experiment(_WS, experiment, now=_NOW)
    run = _run()
    store.record_run(_WS, run, now=_NOW)
    model = RegisteredModelVersion(
        model_id=ModelId("model-1"),
        version=ModelVersion("1"),
        source_run_id=run.id,
        artifact_ref="artifact://model-1",
        artifact_digest="sha256:model",
        framework="sklearn",
        signature=ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
    )

    store.register_model(_WS, model, now=_NOW)

    assert store.get_experiment(_WS, experiment.id) == experiment
    assert store.get_run(_WS, run.id) == run
    assert store.get_model(_WS, model.model_id, model.version) == model


def test_ml_run_id_reuse_with_different_content_fails_closed(tmp_path: Path) -> None:
    store, _catalog = _stores(tmp_path / "ronin.sqlite3")
    store.put_experiment(_WS, Experiment(ExperimentId("exp-1"), "Baseline"), now=_NOW)
    store.record_run(_WS, _run(), now=_NOW)
    conflicting = MLRunRecord(
        id=MLRunId("run-1"),
        experiment_id=ExperimentId("exp-1"),
        execution_ref="job-2/run-2/attempt-1",
        source_revision="git:def456",
        datasets=(_DATA,),
    )

    with pytest.raises(MLConflict):
        store.record_run(_WS, conflicting, now=_NOW)


def test_ml_parameters_reject_credential_bearing_keys() -> None:
    with pytest.raises(ValueError, match="credential-bearing"):
        MLRunRecord(
            id=MLRunId("run-1"),
            experiment_id=ExperimentId("exp-1"),
            execution_ref="job-1/run-1/attempt-1",
            source_revision="git:abc123",
            datasets=(_DATA,),
            parameters=(("api_key", "not-allowed"),),
        )
