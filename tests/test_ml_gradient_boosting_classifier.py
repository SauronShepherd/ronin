from studio_ml.runtime import TrainingSpec, predict_tabular, train_tabular


def test_binary_gradient_boosting_classifier_is_declarative() -> None:
    rows = [{"x": value, "target": "low" if value < 6 else "high"} for value in range(14)]
    spec = TrainingSpec(
        "classification",
        "gradient_boosting_classifier",
        ("x",),
        "target",
        test_fraction=0.2,
        parameters=(("n_estimators", 4), ("max_depth", 2), ("learning_rate", 0.1)),
    )
    model = train_tabular(rows, spec)
    assert predict_tabular(model.artifact_bytes, [{"x": 1}, {"x": 12}]) == ("low", "high")
