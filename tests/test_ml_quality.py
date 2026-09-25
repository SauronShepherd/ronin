from studio_core.catalog import AssetId, AssetRef, AssetVersion
from studio_ml import FeatureSpec, Lab, profile_and_validate


def lab() -> Lab:
    return Lab(
        id="lab-quality",
        name="Quality",
        project_id="project-1",
        dataset=AssetRef(AssetId("dataset"), AssetVersion("v1")),
        target="label",
        task="classification",
        features=(FeatureSpec("value"),),
        backend_id="local.sklearn",
        seed=7,
        test_fraction=0.25,
    )


def test_profile_reports_columns_and_classification_quality() -> None:
    report = profile_and_validate(
        lab(),
        [
            {"value": 1, "label": "yes"},
            {"value": 2, "label": "yes"},
            {"value": 3, "label": "no"},
            {"value": 4, "label": "no"},
        ],
    )
    assert report.passed is True
    assert report.row_count == 4
    assert report.profiles[0].name == "label"
    assert report.profiles[0].distinct_count == 2


def test_quality_gate_rejects_single_class_and_small_dataset() -> None:
    report = profile_and_validate(lab(), [{"value": 1, "label": "yes"}] * 3)
    assert report.passed is False
    assert any("minimum" in failure for failure in report.failures)
    assert any("two classes" in failure for failure in report.failures)
