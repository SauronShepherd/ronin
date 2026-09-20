from studio_ml.runtime import TrainingSpec, predict_tabular, train_tabular


def test_gradient_boosting_regressor_uses_declarative_tree_artifact() -> None:
    rows = [{"x": value, "target": float(value * value)} for value in range(12)]
    spec = TrainingSpec(
        "regression", "gradient_boosting_regressor", ("x",), "target", test_fraction=0.2,
        parameters=(("n_estimators", 4), ("max_depth", 2), ("learning_rate", 0.1)),
    )
    model = train_tabular(rows, spec)
    assert b"learning_rate" in model.artifact_bytes
    prediction = predict_tabular(model.artifact_bytes, [{"x": 2}, {"x": 9}])
    assert len(prediction) == 2
