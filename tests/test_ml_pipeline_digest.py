from __future__ import annotations

import hashlib

from studio_core import WorkspaceId
from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml import PipelineIR, PipelineNode
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.services import InMemoryMLLabStore, LabService


def test_pipeline_digest_is_sha256_of_canonical_json() -> None:
    pipeline = PipelineIR(
        (PipelineNode("profile", "profile"), PipelineNode("train", "train", ("profile",))),
        parameters=(("task", "classification"), ("seed", "17")),
    )

    assert pipeline.digest == hashlib.sha256(pipeline.to_json().encode("utf-8")).hexdigest()


def test_pipeline_digest_changes_when_execution_parameters_change() -> None:
    first = PipelineIR((PipelineNode("train", "train"),), parameters=(("seed", "17"),))
    second = PipelineIR((PipelineNode("train", "train"),), parameters=(("seed", "18"),))

    assert first.digest != second.digest


def test_compiled_pipeline_digest_pins_complete_lab_identity() -> None:
    workspace = WorkspaceId("ws-1")
    first_lab = Lab(
        "lab-1",
        "Lab",
        "project-1",
        AssetRef(AssetId("dataset-1"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("age"),),
    )
    changed_lab = Lab(
        "lab-1",
        "Lab",
        "project-1",
        AssetRef(AssetId("dataset-1"), AssetVersion("v1")),
        "target",
        "classification",
        (FeatureSpec("income"),),
    )

    first = LabService(InMemoryMLLabStore())
    second = LabService(InMemoryMLLabStore())
    first.create(workspace, first_lab)
    second.create(workspace, changed_lab)
    first_pipeline = first.compile(workspace, first_lab.id)
    second_pipeline = second.compile(workspace, changed_lab.id)

    assert dict(first_pipeline.parameters)["lab_digest"] == first_lab.digest
    assert first_pipeline.digest != second_pipeline.digest
