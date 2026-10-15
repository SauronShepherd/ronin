"""Local runner contract tests."""
# ruff: noqa: E501

from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.runner import LocalExperimentRunner


def _lab() -> Lab:
    return Lab(
        "churn",
        "Churn",
        "crm",
        AssetRef(AssetId("customers"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("x", "numeric"),),
    )


def _rows() -> list[dict[str, object]]:
    return [{"x": value, "target": value % 2} for value in range(1, 21)]


def test_local_runner_returns_portable_result_deterministically() -> None:
    runner = LocalExperimentRunner()
    first = runner.run(_lab(), _rows())
    second = runner.run(_lab(), _rows())
    assert first.to_payload() == second.to_payload()
    assert first.artifact_digest.startswith("sha256:")
    assert first.row_count == 20


def test_local_runner_applies_effective_hyperparameters() -> None:
    runner = LocalExperimentRunner()
    default = runner.run(_lab(), _rows())
    tuned = runner.run(_lab(), _rows(), (("C", 0.1), ("max_iter", 200)))
    assert default.artifact_digest != tuned.artifact_digest
    assert b"hyperparameters" in tuned.model.artifact_bytes
