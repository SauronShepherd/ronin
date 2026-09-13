from decimal import Decimal
from pathlib import Path

from studio_core import WorkspaceId
from studio_finops import (
    BudgetPolicy,
    RateCard,
    SqliteFinOpsStore,
    UsageRecord,
    evaluate_budget,
    price_usage,
)
from studio_observability import (
    AlertRule,
    MetricPoint,
    SqliteTelemetryStore,
    alert_notification,
    evaluate_alert,
)
from studio_orchestrator import Instant


_T0 = Instant("2026-09-13T10:00:00.000000Z")
_T1 = Instant("2026-09-13T10:05:00.000000Z")
_T2 = Instant("2026-09-13T10:10:00.000000Z")


def test_alert_opens_and_resolves_from_latest_metric(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    rule = store.put_alert_rule(
        AlertRule(
            "queue-lag",
            "Queue lag high",
            "scheduler.queue_lag",
            "gt",
            10.0,
            (("workspace", "ws"),),
        )
    )
    store.record_metric(
        MetricPoint(
            "scheduler.queue_lag",
            25.0,
            "tasks",
            "gauge",
            _T0,
            (("workspace", "ws"),),
        )
    )
    opened = evaluate_alert(store, rule, now=_T1)
    assert opened.changed
    assert opened.current is not None
    assert opened.current.status == "open"
    notification = alert_notification(opened, now=_T1)
    assert notification is not None
    assert notification.attributes[1] == ("rule_id", "queue-lag")

    store.record_metric(
        MetricPoint(
            "scheduler.queue_lag",
            3.0,
            "tasks",
            "gauge",
            _T2,
            (("workspace", "ws"),),
        )
    )
    resolved = evaluate_alert(store, rule, now=_T2)
    assert resolved.changed
    assert resolved.current is not None
    assert resolved.current.status == "resolved"


def test_finops_keeps_actual_and_estimated_cost_separate(tmp_path: Path) -> None:
    store = SqliteFinOpsStore(tmp_path / "finops.sqlite")
    workspace = WorkspaceId("workspace")
    store.put_rate_card(
        RateCard(
            "cpu-rate",
            "cpu_second",
            "seconds",
            "USD",
            Decimal("0.01"),
            Instant("2026-09-01T00:00:00.000000Z"),
        )
    )
    actual_usage = UsageRecord(
        "usage-actual",
        workspace,
        "cpu_second",
        Decimal("100"),
        "seconds",
        _T0,
        _T1,
        "run:actual",
        "actual",
    )
    estimated_usage = UsageRecord(
        "usage-estimated",
        workspace,
        "cpu_second",
        Decimal("50"),
        "seconds",
        _T1,
        _T2,
        "planner:estimate",
        "estimated",
    )
    price_usage(store, actual_usage)
    price_usage(store, estimated_usage)
    budget = BudgetPolicy(
        "daily",
        workspace,
        "USD",
        Decimal("1.20"),
        Instant("2026-09-13T00:00:00.000000Z"),
        Instant("2026-09-14T00:00:00.000000Z"),
        "notify",
    )
    evaluation = evaluate_budget(store, budget)
    assert evaluation.actual_cost == Decimal("1.00")
    assert evaluation.estimated_cost == Decimal("0.50")
    assert evaluation.total_cost == Decimal("1.50")
    assert evaluation.exceeded
    assert evaluation.recommended_action == "notify"


def test_rate_card_identity_is_immutable(tmp_path: Path) -> None:
    store = SqliteFinOpsStore(tmp_path / "finops.sqlite")
    rate = RateCard(
        "cpu-rate",
        "cpu_second",
        "seconds",
        "USD",
        Decimal("0.01"),
        Instant("2026-09-01T00:00:00.000000Z"),
    )
    assert store.put_rate_card(rate) == rate
    assert store.put_rate_card(rate) == rate
