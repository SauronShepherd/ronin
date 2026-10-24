from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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
from studio_execution import DurableExecutionService
from studio_ml.domain import FeatureDefinition, FeatureSpec, Lab
from studio_ml.orchestration import ExecutionSnapshot, JobStoreExecutionStore
from studio_ml.postgres import PostgresMLLabStore
from studio_ml.registry_bundle import (
    commit_ml_registry_bundle_import,
    export_ml_registry_bundle,
)
from studio_ml.services import FeatureDefinitionConflict
from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState
from studio_storage import PostgresJobReadPort, PostgresMetadataStore, PostgresMLStore
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
    assert metadata.list_revisions(workspace_id, asset_id) == (
        AssetRevision(ref, content_digest="a" * 64),
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


def test_postgres_ml_lab_v1_round_trips_clustering_and_unknown_metadata() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresMLLabStore(dsn, application_name="ronin-ml-lab-qualification")
    store.migrate()
    suffix = uuid4().hex
    workspace_id = WorkspaceId(f"ml-lab-ws-{suffix}")
    store.create_workspace(Workspace(workspace_id, "ML Lab qualification"), now=NOW)
    lab = Lab(
        f"lab-{suffix}",
        "Contract v1 clustering",
        "project-1",
        AssetRef(AssetId(f"dataset-{suffix}"), AssetVersion("sha256:fixture-v1")),
        None,
        "clustering",
        (FeatureSpec("age", "numeric"),),
        test_fraction=0.75,
        metadata={"x-ui": {"labels": ["review", {"collapsed": True}]}},
    )

    assert store.put_lab(workspace_id, lab) == lab
    assert store.get_lab(workspace_id, lab.id) == lab
    assert store.list_labs(workspace_id) == (lab,)


def test_postgres_shared_job_store_claim_target_and_cancel_fence() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    metadata = PostgresMetadataStore(dsn, application_name="ronin-ml-jobs-qualification")
    metadata.migrate()
    service = DurableExecutionService(PostgresJobReadPort(dsn, application_name="ronin-ml-jobs"))
    adapter = JobStoreExecutionStore(service)
    snapshot = ExecutionSnapshot(
        run_id=f"run-{suffix}",
        state="queued",
        workspace_id=f"workspace-{suffix}",
        lab_id="lab",
        lab_digest="a" * 64,
        request_digest="b" * 64,
        lab_json="{}",
        rows_json="[]",
    )
    other_id = JobId(f"other-{suffix}")
    now = NOW
    asyncio.run(
        service.submit(
            Job(
                id=other_id,
                project_id=snapshot.workspace_id,
                idempotency_key=f"other-{suffix}",
                request_digest="c" * 64,
                state=JobState.QUEUED,
                created_at=now,
                updated_at=now,
                target="unrelated.target",
            ),
            Run(
                id=RunId(f"other-run-{suffix}"),
                job_id=other_id,
                ordinal=1,
                state=RunState.PENDING,
                not_before=now,
                created_at=now,
                updated_at=now,
            ),
        )
    )
    try:
        adapter.create(snapshot)
        claim = adapter.claim_next(f"worker-{suffix}")
        assert claim is not None
        assert claim.run_id == snapshot.run_id
        assert adapter.cancel(snapshot.workspace_id, snapshot.run_id).state == "cancelled"
        with pytest.raises(Exception, match="lease|ownership|cancel|terminal"):
            adapter.finish_claim(claim, state="succeeded", result_payload={"late": True})
        status = adapter.get(snapshot.workspace_id, snapshot.run_id)
        assert status is not None
        assert status.state == "cancelled"
    finally:
        asyncio.run(service.aclose())


def test_postgres_ml_reference_list_limits_fail_closed() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresMLStore(dsn, application_name="ronin-ml-retention-bounds")
    store.migrate()
    suffix = uuid4().hex
    workspace_id = WorkspaceId(f"retention-ws-{suffix}")
    store.create_workspace(Workspace(workspace_id, "Retention bounds"), now=NOW)
    experiment = Experiment(ExperimentId(f"retention-exp-{suffix}"), "Retention bounds")
    store.put_experiment(workspace_id, experiment, now=NOW)
    dataset_ref = AssetRef(AssetId(f"retention-dataset-{suffix}"), AssetVersion("v1"))
    store.create_asset(
        workspace_id,
        CatalogAsset(dataset_ref.asset_id, "dataset", "Retention dataset"),
        now=NOW,
    )
    store.put_revision(workspace_id, AssetRevision(dataset_ref, content_digest="d" * 64), now=NOW)
    runs = tuple(
        MLRunRecord(
            MLRunId(f"retention-run-{suffix}-{index}"),
            experiment.id,
            f"execution://{suffix}/{index}",
            "revision-a",
            (dataset_ref,),
        )
        for index in range(2)
    )
    for run in runs:
        store.record_run(workspace_id, run, now=NOW)
    assert store.list_runs(workspace_id, limit=2) == runs
    with pytest.raises(ValueError, match="ML run inventory exceeded"):
        store.list_runs(workspace_id, limit=1)


def test_postgres_ml_node_checkpoint_survives_service_reopen() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    PostgresMetadataStore(dsn, application_name="ronin-ml-checkpoint-qualification").migrate()
    service = DurableExecutionService(
        PostgresJobReadPort(dsn, application_name="ronin-ml-checkpoint")
    )
    adapter = JobStoreExecutionStore(service)
    snapshot = ExecutionSnapshot(
        run_id=f"checkpoint-{suffix}",
        state="queued",
        workspace_id=f"workspace-{suffix}",
        lab_id="lab",
        lab_digest="a" * 64,
        pipeline_digest="b" * 64,
        request_digest="c" * 64,
        lab_json="{}",
        pipeline_json="{}",
        rows_json="[]",
    )
    try:
        adapter.create(snapshot)
        claim = adapter.claim_next(f"worker-{suffix}")
        assert claim is not None
        adapter.save_node_checkpoint(
            claim,
            "profile",
            {"kind": "profile", "value": {"row_count": 4}},
        )
        adapter.finish_claim(claim, state="succeeded", result_payload={"checkpointed": True})
    finally:
        asyncio.run(service.aclose())

    reopened_service = DurableExecutionService(
        PostgresJobReadPort(dsn, application_name="ronin-ml-checkpoint-reopen")
    )
    try:
        reopened_adapter = JobStoreExecutionStore(reopened_service)
        assert reopened_adapter.node_checkpoints(claim) == {
            "profile": {"kind": "profile", "value": {"row_count": 4}}
        }
    finally:
        asyncio.run(reopened_service.aclose())


def test_postgres_shared_job_claim_racing_cancel_finishes_without_deadlock() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    PostgresMetadataStore(dsn, application_name="ronin-ml-race-qualification").migrate()
    service = DurableExecutionService(PostgresJobReadPort(dsn, application_name="ronin-ml-race"))
    adapter = JobStoreExecutionStore(service)
    try:
        for index in range(12):
            run_id = f"race-{suffix}-{index}"
            workspace_id = f"workspace-{suffix}-{index}"
            adapter.create(
                ExecutionSnapshot(
                    run_id=run_id,
                    state="queued",
                    workspace_id=workspace_id,
                    lab_id="lab",
                    lab_digest="a" * 64,
                    request_digest=(f"{index:x}" * 64),
                    lab_json="{}",
                    rows_json="[]",
                )
            )
            barrier = Barrier(3)

            def claim(
                rendezvous: Barrier = barrier,
                claim_owner: str = f"claim-{suffix}-{index}",
            ):
                rendezvous.wait()
                return adapter.claim_next(claim_owner)

            def cancel(
                rendezvous: Barrier = barrier,
                target_workspace: str = workspace_id,
                target_run: str = run_id,
            ):
                rendezvous.wait()
                return adapter.cancel(target_workspace, target_run)

            with ThreadPoolExecutor(max_workers=2) as pool:
                claimed_future = pool.submit(claim)
                cancelled_future = pool.submit(cancel)
                barrier.wait()
                claimed_future.result(timeout=10)
                cancelled = cancelled_future.result(timeout=10)
            assert cancelled.state == "cancelled"
            status = adapter.get(workspace_id, run_id)
            assert status is not None
            assert status.state == "cancelled"
    finally:
        asyncio.run(service.aclose())


def _create_registry_bundle_dataset(
    store: PostgresMetadataStore,
    workspace_id: WorkspaceId,
    suffix: str,
) -> AssetRef:
    ref = AssetRef(AssetId(f"bundle-dataset-{suffix}"), AssetVersion("v1"))
    store.create_asset(
        workspace_id,
        CatalogAsset(ref.asset_id, "dataset", "ML Bundle dataset"),
        now=NOW,
    )
    store.put_revision(
        workspace_id,
        AssetRevision(ref, content_digest="e" * 64),
        now=NOW,
    )
    return ref


def test_postgres_ml_registry_bundle_is_atomic_concurrent_and_replayable(tmp_path) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    source_id = WorkspaceId(f"bundle-source-{suffix}")
    target_id = WorkspaceId(f"bundle-target-{suffix}")
    source = PostgresMLStore(dsn, application_name="ronin-ml-bundle-source")
    target = PostgresMLStore(dsn, application_name="ronin-ml-bundle-target")
    source_features = PostgresMLLabStore(dsn, application_name="ronin-ml-bundle-source-features")
    target_features = PostgresMLLabStore(dsn, application_name="ronin-ml-bundle-target-features")
    source.create_workspace(Workspace(source_id, "ML Bundle source"), now=NOW)
    target.create_workspace(Workspace(target_id, "ML Bundle target"), now=NOW)
    source_ref = _create_registry_bundle_dataset(source, source_id, suffix)
    _create_registry_bundle_dataset(target, target_id, suffix)

    experiment = Experiment(ExperimentId(f"bundle-experiment-{suffix}"), "ML Bundle")
    source.put_experiment(source_id, experiment, now=NOW)
    run = MLRunRecord(
        MLRunId(f"bundle-run-{suffix}"),
        experiment.id,
        f"execution://bundle/{suffix}",
        "revision-bundle",
        (source_ref,),
        metrics=(MetricValue("accuracy", 0.97),),
    )
    source.record_run(source_id, run, now=NOW)
    model = RegisteredModelVersion(
        ModelId(f"bundle-model-{suffix}"),
        ModelVersion("1"),
        run.id,
        f"artifact://bundle/{suffix}",
        "f" * 64,
        "scikit-learn",
        ModelSignature((("feature", "float"),), (("prediction", "float"),)),
        stage="champion",
    )
    source.register_model(source_id, model, now=NOW)
    evaluation = ModelEvaluation(
        model.model_id,
        model.version,
        source_ref,
        "passed",
        (MetricValue("accuracy", 0.97),),
        f"execution://evaluation/{suffix}",
    )
    source.record_evaluation(source_id, evaluation, now=NOW)
    feature = FeatureDefinition(
        f"bundle-feature-{suffix}",
        "Bundle feature",
        f"project-{suffix}",
        source_ref,
        (FeatureSpec("feature", "numeric"),),
    )
    source_features.put_feature_definition(source_id, feature)
    bundle = tmp_path / f"ml-registry-{suffix}.ronin-bundle.zip"
    export_ml_registry_bundle(source_id, source, bundle, feature_store=source_features)

    barrier = Barrier(3)

    def import_bundle() -> None:
        barrier.wait(timeout=10)
        commit_ml_registry_bundle_import(
            bundle,
            target_id,
            target,
            now=NOW,
            feature_store=target_features,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        imports = (pool.submit(import_bundle), pool.submit(import_bundle))
        barrier.wait(timeout=10)
        for future in imports:
            future.result(timeout=15)

    reopened = PostgresMLStore(dsn, application_name="ronin-ml-bundle-replay")
    reopened_features = PostgresMLLabStore(dsn, application_name="ronin-ml-bundle-replay-features")
    commit_ml_registry_bundle_import(
        bundle,
        target_id,
        reopened,
        now=NOW,
        feature_store=reopened_features,
    )
    assert reopened.list_experiments(target_id) == (experiment,)
    assert reopened.list_runs(target_id) == (run,)
    assert reopened.list_models(target_id) == (model,)
    assert reopened.list_evaluations(target_id, model.model_id, model.version) == (evaluation,)
    assert reopened_features.list_feature_definitions(target_id) == (feature,)


def test_postgres_ml_registry_bundle_late_model_conflict_rolls_back_all_rows(tmp_path) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    source_id = WorkspaceId(f"bundle-conflict-source-{suffix}")
    target_id = WorkspaceId(f"bundle-conflict-target-{suffix}")
    source = PostgresMLStore(dsn, application_name="ronin-ml-bundle-conflict-source")
    target = PostgresMLStore(dsn, application_name="ronin-ml-bundle-conflict-target")
    source.create_workspace(Workspace(source_id, "Bundle conflict source"), now=NOW)
    target.create_workspace(Workspace(target_id, "Bundle conflict target"), now=NOW)
    source_ref = _create_registry_bundle_dataset(source, source_id, suffix)
    _create_registry_bundle_dataset(target, target_id, suffix)

    imported_experiment = Experiment(ExperimentId(f"new-experiment-{suffix}"), "Imported")
    source.put_experiment(source_id, imported_experiment, now=NOW)
    imported_run = MLRunRecord(
        MLRunId(f"new-run-{suffix}"),
        imported_experiment.id,
        f"execution://new/{suffix}",
        "revision-new",
        (source_ref,),
    )
    source.record_run(source_id, imported_run, now=NOW)
    model_id = ModelId(f"conflicting-model-{suffix}")
    source_model = RegisteredModelVersion(
        model_id,
        ModelVersion("1"),
        imported_run.id,
        f"artifact://source/{suffix}",
        "a" * 64,
        "scikit-learn",
        ModelSignature((("feature", "float"),), (("prediction", "float"),)),
    )
    source.register_model(source_id, source_model, now=NOW)
    bundle = tmp_path / f"ml-registry-conflict-{suffix}.ronin-bundle.zip"
    export_ml_registry_bundle(source_id, source, bundle)

    existing_experiment = Experiment(ExperimentId(f"existing-experiment-{suffix}"), "Existing")
    target.put_experiment(target_id, existing_experiment, now=NOW)
    existing_run = MLRunRecord(
        MLRunId(f"existing-run-{suffix}"),
        existing_experiment.id,
        f"execution://existing/{suffix}",
        "revision-existing",
        (source_ref,),
    )
    target.record_run(target_id, existing_run, now=NOW)
    existing_model = RegisteredModelVersion(
        model_id,
        ModelVersion("1"),
        existing_run.id,
        f"artifact://target/{suffix}",
        "b" * 64,
        "scikit-learn",
        source_model.signature,
    )
    target.register_model(target_id, existing_model, now=NOW)

    with pytest.raises(MLConflict, match="model version already exists"):
        commit_ml_registry_bundle_import(bundle, target_id, target, now=NOW)

    assert target.get_experiment(target_id, imported_experiment.id) is None
    assert target.get_run(target_id, imported_run.id) is None
    assert target.get_model(target_id, model_id, ModelVersion("1")) == existing_model


def test_postgres_ml_registry_bundle_missing_run_dataset_rolls_back_experiment(tmp_path) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    source_id = WorkspaceId(f"bundle-missing-source-{suffix}")
    target_id = WorkspaceId(f"bundle-missing-target-{suffix}")
    source = PostgresMLStore(dsn, application_name="ronin-ml-bundle-missing-source")
    target = PostgresMLStore(dsn, application_name="ronin-ml-bundle-missing-target")
    source.create_workspace(Workspace(source_id, "Bundle missing source"), now=NOW)
    target.create_workspace(Workspace(target_id, "Bundle missing target"), now=NOW)
    source_ref = _create_registry_bundle_dataset(source, source_id, suffix)
    experiment = Experiment(ExperimentId(f"missing-dataset-experiment-{suffix}"), "Imported")
    source.put_experiment(source_id, experiment, now=NOW)
    run = MLRunRecord(
        MLRunId(f"missing-dataset-run-{suffix}"),
        experiment.id,
        f"execution://missing-dataset/{suffix}",
        "revision-missing",
        (source_ref,),
    )
    source.record_run(source_id, run, now=NOW)
    bundle = tmp_path / f"ml-registry-missing-dataset-{suffix}.ronin-bundle.zip"
    export_ml_registry_bundle(source_id, source, bundle)

    with pytest.raises(CatalogAssetNotFound):
        commit_ml_registry_bundle_import(bundle, target_id, target, now=NOW)

    assert target.get_experiment(target_id, experiment.id) is None
    assert target.get_run(target_id, run.id) is None


@pytest.mark.parametrize(
    "cancel_after_write",
    [False, True],
    ids=("feature-conflict", "cancel-after-feature-write"),
)
def test_postgres_ml_registry_bundle_feature_failure_rolls_back_experiment(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    cancel_after_write: bool,
) -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    suffix = uuid4().hex
    source_id = WorkspaceId(f"bundle-feature-source-{suffix}")
    target_id = WorkspaceId(f"bundle-feature-target-{suffix}")
    source = PostgresMLStore(dsn, application_name="ronin-ml-bundle-feature-source")
    target = PostgresMLStore(dsn, application_name="ronin-ml-bundle-feature-target")
    source_features = PostgresMLLabStore(
        dsn, application_name="ronin-ml-bundle-feature-source-store"
    )
    target_features = PostgresMLLabStore(
        dsn, application_name="ronin-ml-bundle-feature-target-store"
    )
    source.create_workspace(Workspace(source_id, "Bundle feature source"), now=NOW)
    target.create_workspace(Workspace(target_id, "Bundle feature target"), now=NOW)
    source_ref = _create_registry_bundle_dataset(source, source_id, suffix)
    target_ref = _create_registry_bundle_dataset(target, target_id, suffix)

    experiment = Experiment(ExperimentId(f"feature-conflict-experiment-{suffix}"), "Imported")
    source.put_experiment(source_id, experiment, now=NOW)
    source_feature = FeatureDefinition(
        f"feature-conflict-{suffix}",
        "Source feature",
        f"project-{suffix}",
        source_ref,
        (FeatureSpec("feature", "numeric"),),
    )
    source_features.put_feature_definition(source_id, source_feature)
    bundle = tmp_path / f"ml-registry-feature-conflict-{suffix}.ronin-bundle.zip"
    export_ml_registry_bundle(source_id, source, bundle, feature_store=source_features)

    existing_feature = FeatureDefinition(
        source_feature.id,
        "Target feature",
        source_feature.project_id,
        target_ref,
        source_feature.features,
        version=source_feature.version,
    )
    if cancel_after_write:

        class ImportCancelled(BaseException):
            pass

        write_feature = target_features.put_feature_definition_in_transaction

        def write_then_cancel(cursor, workspace_id, definition):
            write_feature(cursor, workspace_id, definition)
            raise ImportCancelled

        monkeypatch.setattr(
            target_features,
            "put_feature_definition_in_transaction",
            write_then_cancel,
        )
        with pytest.raises(ImportCancelled):
            commit_ml_registry_bundle_import(
                bundle,
                target_id,
                target,
                now=NOW,
                feature_store=target_features,
            )
        expected_features = ()
    else:
        target_features.put_feature_definition(target_id, existing_feature)
        with pytest.raises(FeatureDefinitionConflict, match="version already exists"):
            commit_ml_registry_bundle_import(
                bundle,
                target_id,
                target,
                now=NOW,
                feature_store=target_features,
            )
        expected_features = (existing_feature,)

    assert target.get_experiment(target_id, experiment.id) is None
    assert target_features.list_feature_definitions(target_id) == expected_features
