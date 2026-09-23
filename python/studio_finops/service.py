"""FinOps pricing, allocation and budget evaluation services."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from studio_core import WorkspaceId
from studio_observability.notifications import NotificationIntent
from studio_orchestrator import Instant

from .contracts import BudgetEvaluation, BudgetPolicy, CostRecord, RateCard, UsageRecord


class RateCardNotFound(KeyError):
    """Raised when usage cannot be priced without fabricating a rate."""


@dataclass(frozen=True, slots=True)
class AllocationSlice:
    dimensions: tuple[tuple[str, str], ...]
    currency: str
    actual: Decimal
    estimated: Decimal

    @property
    def total(self) -> Decimal:
        return self.actual + self.estimated


@dataclass(frozen=True, slots=True)
class CostForecast:
    """An estimate derived from observed cost, never an actual ledger entry."""

    schema: str
    source_ref: str
    currency: str
    observed_cost: Decimal
    elapsed_fraction: Decimal
    projected_cost: Decimal

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_ref": self.source_ref,
            "currency": self.currency,
            "observed_cost": str(self.observed_cost),
            "elapsed_fraction": str(self.elapsed_fraction),
            "projected_cost": str(self.projected_cost),
            "provenance": "estimated",
        }


@runtime_checkable
class FinOpsStore(Protocol):
    def record_usage(self, usage: UsageRecord) -> UsageRecord: ...

    def list_usage(
        self,
        workspace_id: WorkspaceId,
        *,
        period_start: Instant | str,
        period_end: Instant | str,
    ) -> tuple[UsageRecord, ...]: ...

    def resolve_rate(
        self,
        resource_type: str,
        unit: str,
        *,
        at: Instant | str,
    ) -> RateCard | None: ...

    def record_cost(self, cost: CostRecord) -> CostRecord: ...

    def list_costs(
        self,
        workspace_id: WorkspaceId,
        *,
        period_start: Instant | str,
        period_end: Instant | str,
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


def allocate_costs(
    store: FinOpsStore,
    workspace_id: WorkspaceId,
    *,
    period_start: Instant | str,
    period_end: Instant | str,
    dimensions: tuple[str, ...] = ("project", "team"),
) -> tuple[AllocationSlice, ...]:
    """Allocate costs from durable usage labels without inventing metadata."""
    if not dimensions or len(dimensions) > 16 or len(set(dimensions)) != len(dimensions):
        raise ValueError("allocation dimensions must be unique and bounded")
    if any(not key or key != key.strip() or "\x00" in key for key in dimensions):
        raise ValueError("allocation dimensions must be trimmed")
    usage = {
        item.id: item
        for item in store.list_usage(workspace_id, period_start=period_start, period_end=period_end)
    }
    costs = store.list_costs(workspace_id, period_start=period_start, period_end=period_end)
    currencies = {cost.currency for cost in costs}
    if len(currencies) > 1:
        raise ValueError("allocation cannot aggregate multiple currencies")
    grouped: dict[tuple[tuple[str, str], ...], list[Decimal]] = {}
    for cost in costs:
        labels = dict(usage[cost.usage_id].labels) if cost.usage_id in usage else {}
        key = tuple((dimension, labels.get(dimension, "unknown")) for dimension in dimensions)
        bucket = grouped.setdefault(key, [Decimal("0"), Decimal("0")])
        bucket[0 if cost.provenance == "actual" else 1] += cost.amount
    currency = next(iter(currencies), "UNKNOWN")
    return tuple(
        AllocationSlice(key, currency, values[0], values[1])
        for key, values in sorted(grouped.items())
    )


def forecast_cost(
    *,
    source_ref: str,
    currency: str,
    observed_cost: Decimal,
    elapsed_fraction: Decimal,
) -> CostForecast:
    """Project observed spend to a period end without changing the ledger."""
    if not source_ref or source_ref != source_ref.strip() or "\x00" in source_ref:
        raise ValueError("forecast source_ref must be non-empty and trimmed")
    if (
        not currency
        or len(currency.strip()) != 3
        or not currency.isascii()
        or not currency.isalpha()
    ):
        raise ValueError("forecast currency must be a three-letter code")
    if observed_cost < 0 or elapsed_fraction <= 0 or elapsed_fraction > 1:
        raise ValueError("forecast values are outside their allowed bounds")
    projected = observed_cost / elapsed_fraction
    return CostForecast(
        "ronin.finops.forecast/v1",
        source_ref,
        currency.upper(),
        observed_cost,
        elapsed_fraction,
        projected,
    )


def _labels_match(
    required: tuple[tuple[str, str], ...],
    actual: tuple[tuple[str, str], ...],
) -> bool:
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
    # Resolve labels from the durable ledger; caller-supplied usage metadata is
    # not an authority for budget decisions.
    del usage_by_id
    usage_by_id = {
        usage.id: usage
        for usage in store.list_usage(
            budget.workspace_id,
            period_start=budget.period_start,
            period_end=budget.period_end,
        )
    }
    actual = Decimal("0")
    estimated = Decimal("0")
    for cost in costs:
        if cost.currency != budget.currency:
            raise ValueError(
                f"budget {budget.id} cannot aggregate cost in currency {cost.currency}"
            )
        if budget.labels:
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


def budget_notification(
    evaluation: BudgetEvaluation,
    *,
    now: Instant | str,
) -> NotificationIntent | None:
    """Create one idempotent notification intent when a budget is exceeded."""

    if not evaluation.exceeded:
        return None
    return NotificationIntent(
        f"budget:{evaluation.budget_id}:{evaluation.total_cost}",
        "budget",
        f"Budget exceeded: {evaluation.budget_id}",
        f"Budget total is {evaluation.total_cost} against a limit of {evaluation.limit}.",
        Instant(now),
        (
            ("budget_id", evaluation.budget_id),
            ("action", evaluation.recommended_action or "notify"),
        ),
    )


def budget_gate(evaluation: BudgetEvaluation) -> bool:
    """Return whether a budget evaluation permits new work to be released."""
    return not (evaluation.exceeded and evaluation.recommended_action == "deny_new_work")


__all__ = (
    "AllocationSlice",
    "CostForecast",
    "FinOpsStore",
    "RateCardNotFound",
    "evaluate_budget",
    "budget_notification",
    "budget_gate",
    "price_usage",
    "allocate_costs",
    "forecast_cost",
)
