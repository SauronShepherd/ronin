from decimal import Decimal
from types import SimpleNamespace

import pytest
from studio_finops import AllocationSlice, allocate_costs


def test_allocation_uses_durable_usage_labels():
    store = type("Store", (), {})()
    store.list_usage = lambda *_args, **_kwargs: (
        SimpleNamespace(id="u1", labels=(("project", "alpha"), ("team", "data"))),
    )
    store.list_costs = lambda *_args, **_kwargs: (
        SimpleNamespace(usage_id="u1", currency="EUR", provenance="actual", amount=Decimal("2.50")),
    )
    result = allocate_costs(store, "ws", period_start="a", period_end="b")
    assert result == (
        AllocationSlice(
            (("project", "alpha"), ("team", "data")), "EUR", Decimal("2.50"), Decimal("0")
        ),
    )


def test_allocation_rejects_mixed_currencies():
    store = type("Store", (), {})()
    store.list_usage = lambda *_args, **_kwargs: ()
    store.list_costs = lambda *_args, **_kwargs: (
        type("Cost", (), {"currency": "EUR"})(),
        type("Cost", (), {"currency": "USD"})(),
    )
    with pytest.raises(ValueError, match="currencies"):
        allocate_costs(store, "ws", period_start="a", period_end="b")
