from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from studio_core import WorkspaceId
from studio_finops import (
    BudgetPolicy,
    CostRecord,
    FinOpsConflict,
    PostgresFinOpsStore,
    RateCard,
    UsageRecord,
    price_usage,
)

_DSN = os.environ.get("RONIN_TEST_POSTGRES_DSN")
if not _DSN:
    pytest.skip("RONIN_TEST_POSTGRES_DSN is not configured", allow_module_level=True)
pytest.importorskip("psycopg")


def test_postgres_finops_write_idempotency_pricing_and_budget_persistence() -> None:
    suffix = uuid4().hex
    workspace = WorkspaceId(f"finops-{suffix}")
    store = PostgresFinOpsStore(_DSN, application_name="ronin-postgres-finops-test")
    usage = UsageRecord(
        f"usage-{suffix}", workspace, "compute", Decimal("2.5"), "hour",
        "2026-11-18T00:00:00.000000Z", "2026-11-18T01:00:00.000000Z", "fixture", "actual",
        (("project", "qualification"),),
    )
    rate = RateCard(
        f"rate-{suffix}", "compute", "hour", "EUR", Decimal("3.20"),
        "2026-01-01T00:00:00.000000Z",
    )
    budget = BudgetPolicy(
        f"budget-{suffix}", workspace, "EUR", Decimal("20"),
        "2026-11-18T00:00:00.000000Z", "2026-11-19T00:00:00.000000Z", "notify",
    )

    assert store.record_usage(usage) == usage
    assert store.record_usage(usage) == usage
    conflicting = UsageRecord(
        usage.id, workspace, "compute", Decimal("9"), "hour", usage.period_start,
        usage.period_end, usage.source_ref, usage.provenance, usage.labels,
    )
    with pytest.raises(FinOpsConflict):
        store.record_usage(conflicting)
    assert store.put_rate_card(rate) == rate
    assert price_usage(store, usage).amount == Decimal("8.00")
    with pytest.raises(FinOpsConflict):
        store.record_cost(CostRecord(usage.id, workspace, Decimal("9.00"), "EUR", "actual", rate.id))
    assert store.list_costs(workspace, period_start=usage.period_start, period_end=usage.period_end)
    assert store.put_budget(budget) == budget
    assert store.list_budgets(workspace) == (budget,)
