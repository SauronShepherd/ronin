from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    Workspace,
    WorkspaceId,
)
from studio_core.ml import (
    Experiment,
    ExperimentId,
    MetricValue,
    MLRunId,
    MLRunRecord,
    ModelEvaluation,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_ml import (
    commit_ml_registry_bundle_import,
    export_ml_registry_bundle,
    list_registered_models,
    plan_ml_registry_bundle_import,
    resolve_champion_model,
)
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.ml import MLConflict, SqliteMLStore
from studio_storage.workspaces import SqliteWorkspaceStore

_NOW = Instant("2026-09-12T00:00:00.000000Z")
_WS = WorkspaceId("ws-1")
_DATA = AssetRef(AssetId("dataset-1"), AssetVersion("v1"))


def test_model_registry_contracts_round_trip_canonically() -> None:
    model = RegisteredModelVersion(
        ModelId("model-1"),
        ModelVersion("1"),
        MLRunId("run-1"),
        "artifact://model-1",
        "sha256:model",
        "sklearn",
        ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
    )
    assert RegisteredModelVersion.from_json(model.to_json()) == model
    evaluation = ModelEvaluation(
        ModelId("model-1"),
        ModelVersion("1"),
        _DATA,
        "passed",
        (MetricValue("accuracy", 0.9),),
        "execution-1",
    )
    assert ModelEvaluation.from_json(evaluation.to_json()) == evaluation


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


def test_ml_registry_bundle_round_trip_preserves_experiments_runs_and_models(
    tmp_path: Path,
) -> None:
    source, _catalog = _stores(tmp_path / "source.sqlite3")
    experiment = Experiment(ExperimentId("exp-1"), "Baseline")
    source.put_experiment(_WS, experiment, now=_NOW)
    run = _run()
    source.record_run(_WS, run, now=_NOW)
    model = RegisteredModelVersion(
        ModelId("model-1"),
        ModelVersion("1"),
        run.id,
        "artifact://model-1",
        "sha256:model",
        "sklearn",
        ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
    )
    source.register_model(_WS, model, now=_NOW)

    bundle = tmp_path / "ml-registry.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)
    plan = plan_ml_registry_bundle_import(bundle)
    assert plan.experiments == (experiment,)
    assert plan.runs == (run,)
    assert plan.models == (model,)

    target, _catalog = _stores(tmp_path / "target.sqlite3")
    commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)
    assert target.list_experiments(_WS) == (experiment,)
    assert target.list_runs(_WS) == (run,)
    assert target.list_models(_WS) == (model,)


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


def test_model_promotion_archives_previous_champion_atomically(tmp_path: Path) -> None:
    store, _catalog = _stores(tmp_path / "ronin.sqlite3")
    store.put_experiment(_WS, Experiment(ExperimentId("exp-1"), "Baseline"), now=_NOW)
    run = _run()
    store.record_run(_WS, run, now=_NOW)
    signature = ModelSignature((("x", "float64"),), (("prediction", "float64"),))
    first = RegisteredModelVersion(
        ModelId("model-1"),
        ModelVersion("1"),
        run.id,
        "artifact://one",
        "sha256:one",
        "sklearn",
        signature,
        "champion",
    )
    second = RegisteredModelVersion(
        ModelId("model-1"),
        ModelVersion("2"),
        run.id,
        "artifact://two",
        "sha256:two",
        "sklearn",
        signature,
    )
    store.register_model(_WS, first, now=_NOW)
    store.register_model(_WS, second, now=_NOW)

    with pytest.raises(MLConflict, match="no passed evaluation"):
        store.promote_model(_WS, second.model_id, second.version, now=_NOW)
    store.record_evaluation(
        _WS,
        ModelEvaluation(
            second.model_id,
            second.version,
            _DATA,
            "passed",
            (MetricValue("accuracy", 0.95),),
            "job-evaluation/run-1",
        ),
        now=_NOW,
    )

    promoted = store.promote_model(_WS, second.model_id, second.version, now=_NOW)

    assert promoted.stage == "champion"
    assert store.get_model(_WS, first.model_id, first.version).stage == "archived"
    assert store.get_model(_WS, second.model_id, second.version).stage == "champion"
    assert resolve_champion_model(store, _WS, second.model_id) == promoted
    assert tuple(model.version.value for model in list_registered_models(store, _WS)) == (
        "1",
        "2",
    )


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
