"""Application persistence service tests."""
# ruff: noqa: E501, ARG002

from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_core.ml import Experiment, MLRunId
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.runner import LocalExperimentRunner
from studio_ml.service import persist_experiment_result


class _Registry:
    def __init__(self) -> None:
        self.experiments: list[Experiment] = []
        self.runs = []

    def put_experiment(self, workspace_id, experiment, *, now=None):
        self.experiments.append(experiment)
        return experiment

    def record_run(self, workspace_id, run, *, now=None):
        self.runs.append(run)
        return run


def test_persist_experiment_result_records_identity_and_run() -> None:
    lab = Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x"),),
    )
    result = LocalExperimentRunner().run(lab, [{"x": n, "target": n % 2} for n in range(1, 21)])
    registry = _Registry()
    run = persist_experiment_result(
        registry,
        WorkspaceId("ws"),
        lab,
        result,
        run_id=MLRunId("run-1"),
        execution_ref="job-1",
        source_revision="git:abc",
        now="2026-01-01T00:00:00.000000Z",
    )
    assert run.experiment_id.value == "churn"
    assert registry.experiments[0].name == "Churn"
    assert registry.runs[0].artifact_refs == (result.artifact_digest,)
