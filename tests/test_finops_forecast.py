from decimal import Decimal

import pytest
from studio_finops import forecast_cost


def test_forecast_is_estimated_and_keeps_currency_source():
    result = forecast_cost(
        source_ref="usage:period-1",
        currency="eur",
        observed_cost=Decimal("2.50"),
        elapsed_fraction=Decimal("0.5"),
    )
    assert result.projected_cost == Decimal("5.00")
    assert result.to_payload()["provenance"] == "estimated"
    assert result.currency == "EUR"


def test_forecast_rejects_zero_elapsed_fraction():
    with pytest.raises(ValueError, match="bounds"):
        forecast_cost(
            source_ref="usage:period-1",
            currency="EUR",
            observed_cost=Decimal("1"),
            elapsed_fraction=Decimal("0"),
        )


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_forecast_rejects_non_finite_inputs(value):
    with pytest.raises(ValueError, match="finite"):
        forecast_cost(
            source_ref="usage:period-1",
            currency="EUR",
            observed_cost=value,
            elapsed_fraction=Decimal("0.5"),
        )
    with pytest.raises(ValueError, match="finite"):
        forecast_cost(
            source_ref="usage:period-1",
            currency="EUR",
            observed_cost=Decimal("1"),
            elapsed_fraction=value,
        )


def test_forecast_rejects_non_finite_projection():
    with pytest.raises(ValueError, match="finite"):
        forecast_cost(
            source_ref="usage:period-1",
            currency="EUR",
            observed_cost=Decimal("1e999999"),
            elapsed_fraction=Decimal("1e-999999"),
        )
