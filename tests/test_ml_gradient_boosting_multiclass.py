from studio_ml.runtime import TrainingSpec, predict_tabular, train_tabular


def test_gradient_boosting_classifier_supports_multiclass_artifacts() -> None:
    rows = [{"x": value, "target": (value % 3)} for value in range(15)]
    spec = TrainingSpec(
        "classification", "gradient_boosting_classifier", ("x",), "target", test_fraction=0.2,
    )
    model = train_tabular(rows, spec)
    assert b"trees" in model.artifact_bytes
    assert len(predict_tabular(model.artifact_bytes, [{"x": 1}, {"x": 7}, {"x": 14}])) == 3
