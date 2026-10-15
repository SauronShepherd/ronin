from __future__ import annotations

import os
from uuid import uuid4

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
from studio_orchestrator import Instant
from studio_storage import PostgresMetadataStore, PostgresMLStore
from studio_storage.catalog import CatalogAssetNotFound
from studio_storage.ml import MLConflict
from studio_storage.workspaces import WorkspaceNotFound

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL qualification requires RONIN_POSTGRES_TEST_DSN",
)

NOW = Instant("2026-10-15T00:00:00.000000Z")


def test_postgres_ml_registry_round_trip_and_conflict_guards() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresMLStore(dsn, application_name="ronin-ml-qualification")
    store.migrate()
    suffix = uuid4().hex
    workspace_id = WorkspaceId(f"ml-ws-{suffix}")
    store.create_workspace(Workspace(workspace_id, "ML qualification"), now=NOW)

    asset_id = AssetId(f"dataset-{suffix}")
    ref = AssetRef(asset_id, AssetVersion("v1"))
    metadata = PostgresMetadataStore(dsn, application_name="ronin-ml-qualification")
    metadata.commit_catalog_import(
        workspace_id,
        (CatalogAsset(asset_id, "dataset", "Training data"),),
        (AssetRevision(ref, content_digest="a" * 64),),
        (),
        now=NOW,
    )

    experiment = Experiment(ExperimentId(f"experiment-{suffix}"), "Qualification")
    assert store.put_experiment(workspace_id, experiment, now=NOW) == experiment
    assert store.get_experiment(workspace_id, experiment.id) == experiment
    assert store.list_experiments(workspace_id) == (experiment,)
    assert store.get_experiment(workspace_id, ExperimentId(f"missing-{suffix}")) is None

    run = MLRunRecord(
        MLRunId(f"run-{suffix}"),
        experiment.id,
        "execution://qualification",
        "revision-a",
        (ref,),
        metrics=(MetricValue("accuracy", 0.98),),
    )
    assert store.record_run(workspace_id, run, now=NOW) == run
    assert store.record_run(workspace_id, run, now=NOW) == run
    assert store.get_run(workspace_id, run.id) == run
    assert store.list_runs(workspace_id) == (run,)
    with pytest.raises(MLConflict, match="already exists"):
        store.record_run(
            workspace_id,
            MLRunRecord(run.id, experiment.id, "other-execution", "revision-b", (ref,)),
            now=NOW,
        )
    with pytest.raises(KeyError, match="missing-experiment"):
        store.record_run(
            workspace_id,
            MLRunRecord(
                MLRunId(f"orphan-{suffix}"),
                ExperimentId("missing-experiment"),
                "execution://orphan",
                "revision-a",
                (ref,),
            ),
            now=NOW,
        )
    with pytest.raises(CatalogAssetNotFound):
        store.record_run(
            workspace_id,
            MLRunRecord(
                MLRunId(f"missing-data-{suffix}"),
                experiment.id,
                "execution://missing-data",
                "revision-a",
                (AssetRef(AssetId("missing-asset"), AssetVersion("v1")),),
            ),
            now=NOW,
        )

    model = RegisteredModelVersion(
        ModelId(f"model-{suffix}"),
        ModelVersion("1"),
        run.id,
        "artifact://model",
        "b" * 64,
        "scikit-learn",
        ModelSignature((("feature", "float"),), (("prediction", "float"),)),
        stage="champion",
    )
    assert store.register_model(workspace_id, model, now=NOW) == model
    assert store.register_model(workspace_id, model, now=NOW) == model
    assert store.get_model(workspace_id, model.model_id, model.version) == model
    assert store.get_champion_model(workspace_id, model.model_id) == model
    assert store.list_models(workspace_id) == (model,)
    assert store.list_models(workspace_id, model.model_id) == (model,)
    with pytest.raises(MLConflict, match="already exists"):
        store.register_model(
            workspace_id,
            RegisteredModelVersion(
                model.model_id,
                model.version,
                run.id,
                "artifact://different",
                "c" * 64,
                "scikit-learn",
                model.signature,
            ),
            now=NOW,
        )

    evaluation = ModelEvaluation(
        model.model_id,
        model.version,
        ref,
        "passed",
        (MetricValue("accuracy", 0.98),),
        "execution://evaluation",
    )
    assert store.record_evaluation(workspace_id, evaluation, now=NOW) == evaluation
    assert store.record_evaluation(workspace_id, evaluation, now=NOW) == evaluation
    assert store.list_evaluations(workspace_id, model.model_id, model.version) == (evaluation,)
    with pytest.raises(KeyError, match="missing-model@1"):
        store.record_evaluation(
            workspace_id,
            ModelEvaluation(
                ModelId("missing-model"),
                model.version,
                ref,
                "passed",
                (MetricValue("accuracy", 0.9),),
                "execution://invalid",
            ),
            now=NOW,
        )


def test_postgres_ml_rejects_mutation_for_archived_workspaces() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresMLStore(dsn, application_name="ronin-ml-qualification")
    store.migrate()
    workspace_id = WorkspaceId(f"archived-ml-{uuid4().hex}")
    metadata = PostgresMetadataStore(dsn, application_name="ronin-ml-qualification")
    workspace = Workspace(workspace_id, "Archived ML qualification")
    metadata.create_workspace(workspace, now=NOW)
    metadata.update_workspace(Workspace(workspace_id, workspace.name, state="archived"), now=NOW)
    with pytest.raises(MLConflict, match="archived workspace"):
        store.put_experiment(workspace_id, Experiment(ExperimentId("blocked"), "Blocked"), now=NOW)
    with pytest.raises(WorkspaceNotFound):
        store.put_experiment(
            WorkspaceId("missing-workspace"),
            Experiment(ExperimentId("missing"), "Missing"),
            now=NOW,
        )
