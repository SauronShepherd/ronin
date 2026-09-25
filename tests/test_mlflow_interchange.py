import pytest

from studio_ml import MLflowSubset


def test_mlflow_subset_round_trips_canonically() -> None:
    value = MLflowSubset(
        "model/customer",
        "3",
        "sklearn",
        "a" * 64,
        (("age", "float64"),),
        (("score", "float64"),),
        (("r2", 0.91),),
    )
    assert MLflowSubset.from_bytes(value.to_bytes()) == value


def test_mlflow_subset_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError, match="invalid shape"):
        MLflowSubset.from_bytes(b'{"schema":"ronin.mlflow-subset/v1"}')
