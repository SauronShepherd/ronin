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
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.orchestration import ExecutionSnapshot, JobStoreExecutionStore
from studio_ml.postgres import PostgresMLLabStore
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
