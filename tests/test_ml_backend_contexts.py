from studio_ml.backends import ModelInspection, PredictionContext, TrainingContext


def test_backend_contexts_are_serialization_safe() -> None:
    training = TrainingContext("dataset://demo", workspace_id="ws", run_id="run-1")
    prediction = PredictionContext("model-1", 2, max_rows=50)
    inspection = ModelInspection(("age", "income"), "scikit-learn", "ronin.sklearn.tabular/v2")
    assert training.dataset_ref == "dataset://demo"
    assert prediction.max_rows == 50
    assert inspection.to_payload()["signature"] == ["age", "income"]
