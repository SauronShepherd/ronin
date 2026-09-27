"""Provenance contract tests."""
# ruff: noqa: E501

from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.provenance import run_record
from studio_ml.runner import LocalExperimentRunner


def test_result_becomes_round_trippable_ml_run_record() -> None:
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
    record = run_record(
        lab, result, run_id="run-1", execution_ref="job-1", source_revision="git:abc"
    )
    assert record.from_json(record.to_json()) == record
    assert record.datasets == (lab.dataset,)
    assert record.artifact_refs == (result.artifact_digest,)
