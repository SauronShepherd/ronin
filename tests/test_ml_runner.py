"""Local runner contract tests."""
# ruff: noqa: E501

import pytest
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab, PipelineIR, PipelineNode
from studio_ml.runner import LocalExperimentRunner
from studio_ml.services import compile_lab_pipeline


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


def test_local_runner_executes_pinned_pipeline_and_rejects_unsupported_graph() -> None:
    lab = _lab()
    runner = LocalExperimentRunner()
    compiled = compile_lab_pipeline(lab)
    reordered = PipelineIR(tuple(reversed(compiled.nodes)), compiled.parameters)

    assert (
        runner.execute_pipeline(lab, _rows(), compiled).to_payload()
        == runner.execute_pipeline(lab, _rows(), reordered).to_payload()
    )

    unsupported = PipelineIR(
        tuple(
            PipelineNode(node.id, "register", node.depends_on)
            if node.kind == "quality_gate"
            else node
            for node in compiled.nodes
        ),
        compiled.parameters,
    )
    with pytest.raises(ValueError, match="exactly one supported node"):
        runner.execute_pipeline(lab, _rows(), unsupported)
