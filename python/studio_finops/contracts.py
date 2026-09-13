"""Provider-neutral FinOps usage, rate-card, cost and budget contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, TypeAlias

from studio_core import WorkspaceId
from studio_orchestrator import Instant

UsageProvenance: TypeAlias = Literal["actual", "estimated"]
BudgetAction: TypeAlias = Literal["notify", "deny_new_work"]


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _decimal(value: Decimal | str, name: str, *, allow_zero: bool = True) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    if parsed < 0 or (not allow_zero and parsed == 0):
        raise ValueError(f"{name} must be {'positive' if not allow_zero else 'non-negative'}")
    return parsed


def _labels(values: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    normalized = tuple(sorted((_text(key, "FinOps label key"), _text(value, "FinOps label value")) for key, value in values))
    keys = [key for key, _ in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("FinOps label keys must be unique")
    return normalized


@dataclass(frozen=True, slots=True)
class UsageRecord:
    id: str
    workspace_id: WorkspaceId
    resource_type: str
    quantity: Decimal
    unit: str
    period_start: Instant
    period_end: Instant
    source_ref: str
    provenance: UsageProvenance
    labels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "usage id")
        _text(self.resource_type, "resource type")
        _text(self.unit, "usage unit")
        _text(self.source_ref, "usage source_ref")
        if self.provenance not in {"actual", "estimated"}:
            raise ValueError("usage provenance must be actual or estimated")
        object.__setattr__(self, "quantity", _decimal(self.quantity, "usage quantity"))
        object.__setattr__(self, "period_start", Instant(self.period_start))
        object.__setattr__(self, "period_end", Instant(self.period_end))
        if str(self.period_end) <= str(self.period_start):
            raise ValueError("usage period_end must be after period_start")
        object.__setattr__(self, "labels", _labels(self.labels))


@dataclass(frozen=True, slots=True)
class RateCard:
    id: str
    resource_type: str
    unit: str
    currency: str
    cost_per_unit: Decimal
    effective_from: Instant

    def __post_init__(self) -> None:
        _text(self.id, "rate card id")
        _text(self.resource_type, "rate resource_type")
        _text(self.unit, "rate unit")
        currency = _text(self.currency, "rate currency").upper()
        if len(currency) != 3:
            raise ValueError("rate currency must be a three-letter currency code")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(
            self,
            "cost_per_unit",
            _decimal(self.cost_per_unit, "cost_per_unit"),
        )
        object.__setattr__(self, "effective_from", Instant(self.effective_from))


@dataclass(frozen=True, slots=True)
class CostRecord:
    usage_id: str
    workspace_id: WorkspaceId
    amount: Decimal
    currency: str
    provenance: UsageProvenance
    rate_card_id: str

    def __post_init__(self) -> None:
        _text(self.usage_id, "cost usage_id")
        _text(self.rate_card_id, "cost rate_card_id")
        object.__setattr__(self, "amount", _decimal(self.amount, "cost amount"))
        currency = _text(self.currency, "cost currency").upper()
        if len(currency) != 3:
            raise ValueError("cost currency must be a three-letter currency code")
        object.__setattr__(self, "currency", currency)
        if self.provenance not in {"actual", "estimated"}:
            raise ValueError("cost provenance must be actual or estimated")


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    id: str
    workspace_id: WorkspaceId
    currency: str
    limit: Decimal
    period_start: Instant
    period_end: Instant
    action: BudgetAction = "notify"
    labels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "budget id")
        currency = _text(self.currency, "budget currency").upper()
        if len(currency) != 3:
            raise ValueError("budget currency must be a three-letter currency code")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "limit", _decimal(self.limit, "budget limit", allow_zero=False))
        object.__setattr__(self, "period_start", Instant(self.period_start))
        object.__setattr__(self, "period_end", Instant(self.period_end))
        if str(self.period_end) <= str(self.period_start):
            raise ValueError("budget period_end must be after period_start")
        if self.action not in {"notify", "deny_new_work"}:
            raise ValueError("unsupported budget action")
        object.__setattr__(self, "labels", _labels(self.labels))


@dataclass(frozen=True, slots=True)
class BudgetEvaluation:
    budget_id: str
    actual_cost: Decimal
    estimated_cost: Decimal
    total_cost: Decimal
    limit: Decimal
    exceeded: bool
    recommended_action: BudgetAction | None


__all__ = (
    "BudgetAction",
    "BudgetEvaluation",
    "BudgetPolicy",
    "CostRecord",
    "RateCard",
    "UsageProvenance",
    "UsageRecord",
)
