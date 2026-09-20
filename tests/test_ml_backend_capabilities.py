from studio_ml.backends import BackendCapabilities, LocalScikitLearnBackend


def test_local_backend_publishes_stable_capabilities() -> None:
    backend = LocalScikitLearnBackend()
    assert backend.capabilities == BackendCapabilities(
        tasks=("classification", "regression", "clustering"),
        algorithms=(
            "logistic_regression", "linear_regression", "decision_tree_classifier",
            "decision_tree_regressor", "random_forest_classifier", "random_forest_regressor",
            "kmeans", "gradient_boosting_regressor", "gradient_boosting_classifier",
        ),
    )
    assert backend.capabilities.to_payload() == {
        "tasks": ["classification", "regression", "clustering"],
        "algorithms": [
            "logistic_regression", "linear_regression", "decision_tree_classifier",
            "decision_tree_regressor", "random_forest_classifier", "random_forest_regressor",
            "kmeans", "gradient_boosting_regressor", "gradient_boosting_classifier",
        ],
        "supports_prediction": True,
        "supports_artifacts": True,
        "supports_explainability": False,
    }
