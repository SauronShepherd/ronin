from studio_ml.runtime import TrainingSpec, predict_tabular, train_tabular


def test_decision_tree_classifier_uses_declarative_artifact() -> None:
    rows = [{"x": value, "target": "low" if value < 5 else "high"} for value in range(10)]
    spec = TrainingSpec(
        "classification", "decision_tree_classifier", ("x",), "target", test_fraction=0.2
    )
    model = train_tabular(rows, spec)
    assert b"children_left" in model.artifact_bytes
    assert predict_tabular(model.artifact_bytes, [{"x": 1}, {"x": 9}]) == ("low", "high")


def test_decision_tree_regressor_predicts_from_artifact() -> None:
    rows = [{"x": value, "target": float(value * 2)} for value in range(10)]
    spec = TrainingSpec(
        "regression", "decision_tree_regressor", ("x",), "target", test_fraction=0.2
    )
    model = train_tabular(rows, spec)
    prediction = predict_tabular(model.artifact_bytes, [{"x": 1}, {"x": 9}])
    assert len(prediction) == 2


def test_random_forest_classifier_uses_tree_ensemble_artifact() -> None:
    rows = [{"x": value, "target": "low" if value < 5 else "high"} for value in range(12)]
    spec = TrainingSpec(
        "classification",
        "random_forest_classifier",
        ("x",),
        "target",
        test_fraction=0.2,
        parameters=(("n_estimators", 3), ("max_depth", 3)),
    )
    model = train_tabular(rows, spec)
    assert b"trees" in model.artifact_bytes
    assert predict_tabular(model.artifact_bytes, [{"x": 1}, {"x": 10}]) == ("low", "high")
