import pytest
from studio_ml import (
    DriftThreshold,
    NumericDrift,
    assess_numeric_drift,
    compare_numeric_drift,
)


def test_numeric_drift_is_deterministic_and_reports_mean_and_variance() -> None:
    result = compare_numeric_drift(
        ({"score": 1}, {"score": 3}),
        ({"score": 2}, {"score": 6}),
        ("score",),
    )
    assert result == (NumericDrift("score", 2, 2, 2.0, 4.0, 2.0, 1.0, 4.0, 3.0),)
    assert result[0].to_payload()["mean_delta"] == 2.0


def test_numeric_drift_rejects_unbounded_or_non_numeric_input() -> None:
    with pytest.raises(ValueError, match="max_rows"):
        compare_numeric_drift(({"score": 1},), ({"score": 2},), ("score",), max_rows=0)
    with pytest.raises(ValueError, match="finite numbers"):
        compare_numeric_drift(({"score": None},), ({"score": 2},), ("score",))
    with pytest.raises(ValueError, match="both windows"):
        compare_numeric_drift(({"score": 1},), (), ("score",))


def test_numeric_drift_assessment_is_explicit_and_deterministic() -> None:
    summaries = compare_numeric_drift(
        ({"score": 1}, {"score": 3}),
        ({"score": 2}, {"score": 6}),
        ("score",),
    )
    assert assess_numeric_drift(summaries, (DriftThreshold("score", 2.0, 3.0),)).status == "ok"
    assessed = assess_numeric_drift(summaries, (DriftThreshold("score", 1.0, 3.0),))
    assert assessed.status == "drifted"
    assert assessed.drifted_features == ("score",)
