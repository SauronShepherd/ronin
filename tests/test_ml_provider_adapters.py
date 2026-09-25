from studio_ml.remote import MLflowBackend, SparkBackend


def test_provider_adapters_have_stable_ids_and_capabilities() -> None:
    def transport(_operation: str, _payload: dict[str, object]) -> dict[str, object]:
        return {"run_id": "r", "status": "queued"}

    mlflow = MLflowBackend(transport)
    spark = SparkBackend(transport)
    assert mlflow.backend_id == "remote.mlflow"
    assert "random_forest_classifier" in mlflow.capabilities.algorithms
    assert spark.backend_id == "remote.spark"
    assert "clustering" in spark.capabilities.tasks
