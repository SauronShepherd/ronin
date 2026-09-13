"""FinOps pricing, allocation and budget evaluation services."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from studio_core import WorkspaceId

from .contracts import BudgetEvaluation, BudgetPolicy, CostRecord, RateCard, UsageRecord


class RateCardNotFound(KeyError):
    """Raised when usage cannot be priced without fabricating a rate."""


@runtime_checkable
class FinOpsStore(Protocol):
    def record_usage(self, usage: UsageRecord) -> UsageRecord: ...

    def resolve_rate(self, resource_type: str, unit: str, *, at: object) -> RateCard | None: ...

    def record_cost(self, cost: CostRecord) -> CostRecord: ...

    def list_costs(
        self,
        workspace_id: WorkspaceId,
        *,
        period_start: object,
        period_end: object,
    ) -> tuple[CostRecord, ...]: ...


def price_usage(store: FinOpsStore, usage: UsageRecord) -> CostRecord:
    """Persist usage, resolve an effective rate, and persist traceable cost."""

    recorded = store.record_usage(usage)
    rate = store.resolve_rate(
        recorded.resource_type,
        recorded.unit,
        at=recorded.period_end,
    )
    if rate is None:
        raise RateCardNotFound(
            f"no rate card for {recorded.resource_type}/{recorded.unit} at {recorded.period_end}"
        )
    amount = recorded.quantity * rate.cost_per_unit
    cost = CostRecord(
        recorded.id,
        recorded.workspace_id,
        amount,
        rate.currency,
        recorded.provenance,
        rate.id,
    )
    return store.record_cost(cost)


def _labels_match(required: tuple[tuple[str, str], ...], actual: tuple[tuple[str, str], ...]) -> bool:
    actual_map = dict(actual)
    return all(actual_map.get(key) == value for key, value in required)


def evaluate_budget(
    store: FinOpsStore,
    budget: BudgetPolicy,
    *,
    usage_by_id: dict[str, UsageRecord] | None = None,
) -> BudgetEvaluation:
    """Evaluate persisted cost without executing the budget action as a side effect."""

    costs = store.list_costs(
        budget.workspace_id,
        period_start=budget.period_start,
        period_end=budget.period_end,
    )
    actual = Decimal("0")
    estimated = Decimal("0")
    for cost in costs:
        if cost.currency != budget.currency:
            raise ValueError(
                f"budget {budget.id} cannot aggregate cost in currency {cost.currency}"
            )
        if budget.labels:
            if usage_by_id is None:
                raise ValueError("label-scoped budget evaluation requires usage_by_id")
            usage = usage_by_id.get(cost.usage_id)
            if usage is None or not _labels_match(budget.labels, usage.labels):
                continue
        if cost.provenance == "actual":
            actual += cost.amount
        else:
            estimated += cost.amount
    total = actual + estimated
    exceeded = total > budget.limit
    return BudgetEvaluation(
        budget.id,
        actual,
        estimated,
        total,
        budget.limit,
        exceeded,
        budget.action if exceeded else None,
    )


__all__ = (
    "FinOpsStore",
    "RateCardNotFound",
    "evaluate_budget",
    "price_usage",
)
