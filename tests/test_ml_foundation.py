from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

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
    FeatureDefinition,
    FeatureDefinitionConflict,
    FeatureSpec,
    SqliteMLLabStore,
    commit_ml_registry_bundle_import,
    export_ml_registry_bundle,
    list_registered_models,
    plan_ml_registry_bundle_import,
    resolve_champion_model,
)
from studio_orchestrator import Instant
from studio_storage.catalog import CatalogAssetNotFound, SqliteCatalogStore
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
        stage="champion",
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


def test_ml_registry_retention_limits_fail_closed(tmp_path: Path) -> None:
    store, _catalog = _stores(tmp_path / "ronin.sqlite3")
    store.put_experiment(_WS, Experiment(ExperimentId("exp-1"), "Baseline"), now=_NOW)
    store.record_run(_WS, _run(), now=_NOW)
    assert store.list_runs(_WS, limit=1) == (_run(),)
    run = _run()
    store.record_run(
        _WS,
        MLRunRecord(
            MLRunId("run-2"),
            run.experiment_id,
            run.execution_ref,
            run.source_revision,
            run.datasets,
            run.parameters,
            run.metrics,
            run.artifact_refs,
        ),
        now=_NOW,
    )
    with pytest.raises(ValueError, match="ML run inventory exceeded"):
        store.list_runs(_WS, limit=1)
    with pytest.raises(ValueError, match="model list limit must be positive"):
        store.list_models(_WS, limit=0)


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
        stage="champion",
    )
    source.register_model(_WS, model, now=_NOW)
    evaluation = ModelEvaluation(
        model.model_id,
        model.version,
        _DATA,
        "passed",
        (MetricValue("accuracy", 0.9),),
        "evaluation-1",
    )
    source.record_evaluation(_WS, evaluation, now=_NOW)

    bundle = tmp_path / "ml-registry.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)
    plan = plan_ml_registry_bundle_import(bundle)
    assert plan.experiments == (experiment,)
    assert plan.runs == (run,)
    assert plan.models == (model,)
    assert plan.evaluations == (evaluation,)

    target_path = tmp_path / "target.sqlite3"
    target, _catalog = _stores(target_path)
    commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)
    reopened_target = SqliteMLStore(target_path, migration_now=_NOW)
    commit_ml_registry_bundle_import(bundle, _WS, reopened_target, now=_NOW)
    assert target.list_experiments(_WS) == (experiment,)
    assert target.list_runs(_WS) == (run,)
    assert target.list_models(_WS) == (model,)
    assert target.list_evaluations(_WS, model.model_id, model.version) == (evaluation,)


def test_concurrent_ml_registry_bundle_import_rolls_back_late_conflicting_bundle(
    tmp_path: Path,
) -> None:
    bundle_paths: list[Path] = []
    for label in ("first", "second"):
        source, _catalog = _stores(tmp_path / f"{label}-source.sqlite3")
        experiment = Experiment(ExperimentId(f"exp-{label}"), label)
        run = MLRunRecord(
            MLRunId(f"run-{label}"),
            experiment.id,
            f"job-{label}/run-1/attempt-1",
            f"git:{label}",
            datasets=(_DATA,),
        )
        model = RegisteredModelVersion(
            ModelId("concurrent-model"),
            ModelVersion("1"),
            run.id,
            f"artifact://{label}",
            f"sha256:{label}",
            "sklearn",
            ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
        )
        source.put_experiment(_WS, experiment, now=_NOW)
        source.record_run(_WS, run, now=_NOW)
        source.register_model(_WS, model, now=_NOW)
        bundle_path = tmp_path / f"{label}.roninbundle"
        export_ml_registry_bundle(_WS, source, bundle_path)
        bundle_paths.append(bundle_path)

    target, _catalog = _stores(tmp_path / "target.sqlite3")
    start = Barrier(3)

    def import_bundle(path: Path) -> str:
        start.wait(timeout=5)
        try:
            commit_ml_registry_bundle_import(path, _WS, target, now=_NOW)
        except MLConflict:
            return "conflict"
        return "imported"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(import_bundle, path) for path in bundle_paths]
        start.wait(timeout=5)
        outcomes = tuple(sorted(future.result(timeout=10) for future in futures))

    assert outcomes == ("conflict", "imported")
    assert len(target.list_experiments(_WS)) == 1
    assert len(target.list_runs(_WS)) == 1
    models = target.list_models(_WS)
    runs = target.list_runs(_WS)
    assert len(models) == 1
    assert models[0].source_run_id == runs[0].id
    assert runs[0].experiment_id == target.list_experiments(_WS)[0].id


def test_cancelled_ml_registry_bundle_import_rolls_back_sqlite_metadata(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    source, _catalog = _stores(source_path)
    source_feature_store = SqliteMLLabStore(source_path, migration_now=_NOW)
    experiment = Experiment(ExperimentId("cancelled-import"), "Must roll back")
    feature = FeatureDefinition(
        "cancel-feature",
        "Cancellation feature",
        "project-1",
        _DATA,
        (FeatureSpec("amount", "numeric"),),
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source_feature_store.put_feature_definition(_WS, feature)
    bundle = tmp_path / "cancelled.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle, feature_store=source_feature_store)

    target_path = tmp_path / "target.sqlite3"
    target, _catalog = _stores(target_path)

    class CancelledFeatureStore(SqliteMLLabStore):
        def put_feature_definition_in_transaction(self, connection, workspace_id, definition):
            del connection, workspace_id, definition
            raise KeyboardInterrupt("simulated import cancellation")

    interrupted_feature_store = CancelledFeatureStore(target_path, migration_now=_NOW)
    with pytest.raises(KeyboardInterrupt, match="simulated import cancellation"):
        commit_ml_registry_bundle_import(
            bundle,
            _WS,
            target,
            now=_NOW,
            feature_store=interrupted_feature_store,
        )

    assert target.list_experiments(_WS) == ()
    assert interrupted_feature_store.list_feature_definitions(_WS) == ()


def test_ml_registry_bundle_rejects_champion_without_passed_evaluation(
    tmp_path: Path,
) -> None:
    source, _source_catalog = _stores(tmp_path / "source.sqlite3")
    experiment = Experiment(ExperimentId("exp-1"), "Baseline")
    run = _run()
    champion = RegisteredModelVersion(
        ModelId("model-1"),
        ModelVersion("1"),
        run.id,
        "artifact://model-1",
        "sha256:model",
        "sklearn",
        ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
        stage="champion",
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source.record_run(_WS, run, now=_NOW)
    source.register_model(_WS, champion, now=_NOW)
    bundle = tmp_path / "unqualified-champion.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)

    target, _target_catalog = _stores(tmp_path / "target.sqlite3")
    with pytest.raises(ValueError, match="champion model requires a passed evaluation"):
        commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)

    assert target.list_experiments(_WS) == ()
    assert target.list_runs(_WS) == ()
    assert target.list_models(_WS) == ()


def test_ml_registry_bundle_wont_replace_an_existing_champion_version(
    tmp_path: Path,
) -> None:
    source, _source_catalog = _stores(tmp_path / "source.sqlite3")
    source_experiment = Experiment(ExperimentId("source-champion-exp"), "Source")
    source_run = MLRunRecord(
        MLRunId("source-champion-run"),
        source_experiment.id,
        "job-source/run-1/attempt-1",
        "git:source",
        datasets=(_DATA,),
    )
    imported_champion = RegisteredModelVersion(
        ModelId("single-champion"),
        ModelVersion("2"),
        source_run.id,
        "artifact://source-champion",
        "sha256:source-champion",
        "sklearn",
        ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
        stage="champion",
    )
    source.put_experiment(_WS, source_experiment, now=_NOW)
    source.record_run(_WS, source_run, now=_NOW)
    source.register_model(_WS, imported_champion, now=_NOW)
    source.record_evaluation(
        _WS,
        ModelEvaluation(
            imported_champion.model_id,
            imported_champion.version,
            _DATA,
            "passed",
            (MetricValue("accuracy", 0.9),),
            "source-champion-evaluation",
        ),
        now=_NOW,
    )
    bundle = tmp_path / "existing-champion.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)

    target, _target_catalog = _stores(tmp_path / "target.sqlite3")
    target_experiment = Experiment(ExperimentId("target-champion-exp"), "Target")
    target_run = MLRunRecord(
        MLRunId("target-champion-run"),
        target_experiment.id,
        "job-target/run-1/attempt-1",
        "git:target",
        datasets=(_DATA,),
    )
    existing_champion = RegisteredModelVersion(
        imported_champion.model_id,
        ModelVersion("1"),
        target_run.id,
        "artifact://target-champion",
        "sha256:target-champion",
        "sklearn",
        imported_champion.signature,
        stage="champion",
    )
    target.put_experiment(_WS, target_experiment, now=_NOW)
    target.record_run(_WS, target_run, now=_NOW)
    target.register_model(_WS, existing_champion, now=_NOW)
    existing_evaluation = ModelEvaluation(
        existing_champion.model_id,
        existing_champion.version,
        _DATA,
        "passed",
        (MetricValue("accuracy", 0.8),),
        "target-champion-evaluation",
    )
    target.record_evaluation(_WS, existing_evaluation, now=_NOW)
    before = (
        target.list_experiments(_WS),
        target.list_runs(_WS),
        target.list_models(_WS),
        target.list_evaluations(_WS, existing_champion.model_id, existing_champion.version),
    )

    with pytest.raises(MLConflict, match="different champion version"):
        commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)

    assert (
        target.list_experiments(_WS),
        target.list_runs(_WS),
        target.list_models(_WS),
        target.list_evaluations(_WS, existing_champion.model_id, existing_champion.version),
    ) == before


def test_ml_registry_bundle_rejects_multiple_champion_versions_for_one_model(
    tmp_path: Path,
) -> None:
    source, _source_catalog = _stores(tmp_path / "source.sqlite3")
    experiment = Experiment(ExperimentId("multi-champion-exp"), "Source")
    source.put_experiment(_WS, experiment, now=_NOW)
    for version in ("1", "2"):
        run = MLRunRecord(
            MLRunId(f"multi-champion-run-{version}"),
            experiment.id,
            f"job-version-{version}/run-1/attempt-1",
            "git:multi-champion",
            datasets=(_DATA,),
        )
        model = RegisteredModelVersion(
            ModelId("multiple-champions"),
            ModelVersion(version),
            run.id,
            f"artifact://model-{version}",
            f"sha256:model-{version}",
            "sklearn",
            ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
            stage="champion",
        )
        source.record_run(_WS, run, now=_NOW)
        source.register_model(_WS, model, now=_NOW)
        source.record_evaluation(
            _WS,
            ModelEvaluation(
                model.model_id,
                model.version,
                _DATA,
                "passed",
                (MetricValue("accuracy", 0.9),),
                f"evaluation-{version}",
            ),
            now=_NOW,
        )
    bundle = tmp_path / "multiple-champions.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)

    target, _target_catalog = _stores(tmp_path / "target.sqlite3")
    with pytest.raises(ValueError, match="multiple champion versions"):
        commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)

    assert target.list_experiments(_WS) == ()
    assert target.list_runs(_WS) == ()
    assert target.list_models(_WS) == ()


def test_ml_registry_bundle_late_model_conflict_rolls_back_all_sqlite_metadata(
    tmp_path: Path,
) -> None:
    source, _source_catalog = _stores(tmp_path / "source.sqlite3")
    experiment = Experiment(ExperimentId("imported-experiment"), "Imported")
    run = MLRunRecord(
        MLRunId("imported-run"),
        experiment.id,
        "job-imported/run-1/attempt-1",
        "git:imported",
        datasets=(_DATA,),
    )
    model = RegisteredModelVersion(
        ModelId("model-collision"),
        ModelVersion("1"),
        run.id,
        "artifact://imported-model",
        "sha256:imported",
        "sklearn",
        ModelSignature((("x", "float64"),), (("prediction", "float64"),)),
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source.record_run(_WS, run, now=_NOW)
    source.register_model(_WS, model, now=_NOW)
    bundle = tmp_path / "ml-conflict.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)

    target, _target_catalog = _stores(tmp_path / "target.sqlite3")
    existing_experiment = Experiment(ExperimentId("existing-experiment"), "Existing")
    existing_run = MLRunRecord(
        MLRunId("existing-run"),
        existing_experiment.id,
        "job-existing/run-1/attempt-1",
        "git:existing",
        datasets=(_DATA,),
    )
    conflicting_model = RegisteredModelVersion(
        model.model_id,
        model.version,
        existing_run.id,
        "artifact://existing-model",
        "sha256:existing",
        "sklearn",
        model.signature,
    )
    target.put_experiment(_WS, existing_experiment, now=_NOW)
    target.record_run(_WS, existing_run, now=_NOW)
    target.register_model(_WS, conflicting_model, now=_NOW)
    before = (
        target.list_experiments(_WS),
        target.list_runs(_WS),
        target.list_models(_WS),
    )

    with pytest.raises(MLConflict, match="model version already exists"):
        commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)

    assert target.get_experiment(_WS, experiment.id) is None
    assert target.get_run(_WS, run.id) is None
    assert (
        target.list_experiments(_WS),
        target.list_runs(_WS),
        target.list_models(_WS),
    ) == before


def test_ml_registry_bundle_missing_run_dataset_rolls_back_all_sqlite_metadata(
    tmp_path: Path,
) -> None:
    source, source_catalog = _stores(tmp_path / "source.sqlite3")
    missing_in_target = AssetRef(AssetId("dataset-2"), AssetVersion("v1"))
    source_catalog.create_asset(
        _WS, CatalogAsset(AssetId("dataset-2"), "dataset", "additional"), now=_NOW
    )
    source_catalog.put_revision(
        _WS, AssetRevision(missing_in_target, content_digest="sha256:data-2"), now=_NOW
    )
    experiment = Experiment(ExperimentId("late-dataset-experiment"), "Imported")
    run = MLRunRecord(
        MLRunId("late-dataset-run"),
        experiment.id,
        "job-late/run-1/attempt-1",
        "git:late",
        datasets=(missing_in_target,),
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source.record_run(_WS, run, now=_NOW)
    bundle = tmp_path / "missing-run-dataset.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle)

    target, _target_catalog = _stores(tmp_path / "target.sqlite3")
    with pytest.raises(CatalogAssetNotFound, match="dataset-2@v1"):
        commit_ml_registry_bundle_import(bundle, _WS, target, now=_NOW)

    assert target.list_experiments(_WS) == ()
    assert target.list_runs(_WS) == ()
    assert target.list_models(_WS) == ()


def test_ml_registry_bundle_missing_feature_dataset_rolls_back_registry_rows(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    source, source_catalog = _stores(source_path)
    source_features = SqliteMLLabStore(source_path, migration_now=_NOW)
    missing_in_target = AssetRef(AssetId("dataset-feature-only"), AssetVersion("v1"))
    source_catalog.create_asset(
        _WS,
        CatalogAsset(AssetId("dataset-feature-only"), "dataset", "feature-only"),
        now=_NOW,
    )
    source_catalog.put_revision(
        _WS,
        AssetRevision(missing_in_target, content_digest="sha256:feature-only"),
        now=_NOW,
    )
    experiment = Experiment(ExperimentId("feature-dataset-experiment"), "Imported")
    feature = FeatureDefinition(
        "feature-missing-target-data",
        "Feature with external dataset",
        "project-1",
        missing_in_target,
        (FeatureSpec("amount", "numeric"),),
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source_features.put_feature_definition(_WS, feature)
    bundle = tmp_path / "missing-feature-dataset.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle, feature_store=source_features)

    target_path = tmp_path / "target.sqlite3"
    target, _target_catalog = _stores(target_path)
    target_features = SqliteMLLabStore(target_path, migration_now=_NOW)
    with pytest.raises(CatalogAssetNotFound, match="dataset-feature-only@v1"):
        commit_ml_registry_bundle_import(
            bundle,
            _WS,
            target,
            now=_NOW,
            feature_store=target_features,
        )

    assert target.list_experiments(_WS) == ()
    assert target_features.list_feature_definitions(_WS) == ()


def test_ml_registry_bundle_feature_conflict_rolls_back_registry_rows(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    source, _source_catalog = _stores(source_path)
    source_feature_store = SqliteMLLabStore(source_path, migration_now=_NOW)
    experiment = Experiment(ExperimentId("feature-import-experiment"), "Imported")
    feature = FeatureDefinition(
        "feature-1",
        "Imported feature",
        "project-1",
        _DATA,
        (FeatureSpec("amount", "numeric"),),
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source_feature_store.put_feature_definition(_WS, feature)
    bundle = tmp_path / "ml-feature-conflict.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle, feature_store=source_feature_store)

    success_path = tmp_path / "feature-success.sqlite3"
    successful_target, _successful_catalog = _stores(success_path)
    successful_feature_store = SqliteMLLabStore(success_path, migration_now=_NOW)
    commit_ml_registry_bundle_import(
        bundle,
        _WS,
        successful_target,
        now=_NOW,
        feature_store=successful_feature_store,
    )
    commit_ml_registry_bundle_import(
        bundle,
        _WS,
        successful_target,
        now=_NOW,
        feature_store=successful_feature_store,
    )
    assert successful_target.list_experiments(_WS) == (experiment,)
    assert successful_feature_store.list_feature_definitions(_WS) == (feature,)

    target_path = tmp_path / "target.sqlite3"
    target, _target_catalog = _stores(target_path)
    target_feature_store = SqliteMLLabStore(target_path, migration_now=_NOW)
    existing_feature = FeatureDefinition(
        feature.id,
        "Existing feature",
        feature.project_id,
        _DATA,
        feature.features,
        version=feature.version,
    )
    target_feature_store.put_feature_definition(_WS, existing_feature)

    with pytest.raises(FeatureDefinitionConflict, match="version already exists"):
        commit_ml_registry_bundle_import(
            bundle,
            _WS,
            target,
            now=_NOW,
            feature_store=target_feature_store,
        )

    assert target.get_experiment(_WS, experiment.id) is None
    assert target_feature_store.list_feature_definitions(_WS) == (existing_feature,)


def test_ml_registry_bundle_rejects_feature_store_on_another_database_before_import(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.sqlite3"
    source, _source_catalog = _stores(source_path)
    source_feature_store = SqliteMLLabStore(source_path, migration_now=_NOW)
    experiment = Experiment(ExperimentId("feature-preflight-experiment"), "Imported")
    feature = FeatureDefinition(
        "feature-preflight",
        "Preflight feature",
        "project-1",
        _DATA,
        (FeatureSpec("amount", "numeric"),),
    )
    source.put_experiment(_WS, experiment, now=_NOW)
    source_feature_store.put_feature_definition(_WS, feature)
    bundle = tmp_path / "ml-feature-preflight.roninbundle"
    export_ml_registry_bundle(_WS, source, bundle, feature_store=source_feature_store)

    target_path = tmp_path / "target.sqlite3"
    target, _target_catalog = _stores(target_path)
    mismatched_feature_store = SqliteMLLabStore(
        tmp_path / "other-features.sqlite3", migration_now=_NOW
    )

    with pytest.raises(ValueError, match="must share one SQLite database"):
        commit_ml_registry_bundle_import(
            bundle,
            _WS,
            target,
            now=_NOW,
            feature_store=mismatched_feature_store,
        )

    assert target.get_experiment(_WS, experiment.id) is None


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
