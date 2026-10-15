from decimal import Decimal
from pathlib import Path

import pytest
from studio_core import WorkspaceId
from studio_finops import (
    BudgetPolicy,
    RateCard,
    SqliteFinOpsStore,
    UsageRecord,
    budget_gate,
    budget_notification,
    evaluate_budget,
    forecast_cost,
    price_usage,
)
from studio_observability import (
    AlertHTTPAdapter,
    AlertRule,
    MetricPoint,
    SqliteTelemetryStore,
    alert_notification,
    evaluate_alert,
)
from studio_observability.alerts import _elapsed_seconds
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


def test_latest_metric_applies_attribute_filter_before_selecting_latest(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    store.record_metric(MetricPoint("jobs", 4.0, "count", "gauge", _T0, (("workspace", "a"),)))
    store.record_metric(MetricPoint("jobs", 9.0, "count", "gauge", _T1, (("workspace", "b"),)))
    result = store.latest_metric("jobs", attribute_filters=(("workspace", "a"),))
    assert result is not None
    assert result.value == 4.0


def test_alert_acknowledgement_is_durable_and_idempotent(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    rule = store.put_alert_rule(AlertRule("ack", "Ack", "metric", "gt", 1.0))
    store.record_metric(MetricPoint("metric", 2.0, "count", "gauge", _T0))
    opened = evaluate_alert(store, rule, now=_T1)
    assert opened.current is not None
    acknowledged = store.acknowledge_alert(rule.id, opened.current.fingerprint, acknowledged_at=_T2)
    assert acknowledged is not None
    assert acknowledged.acknowledged_at == _T2
    assert (
        store.acknowledge_alert(rule.id, opened.current.fingerprint, acknowledged_at=_T2)
        == acknowledged
    )
    store.record_metric(MetricPoint("metric", 3.0, "count", "gauge", _T2))
    refreshed = evaluate_alert(store, rule, now=_T2)
    assert refreshed.current is not None
    assert refreshed.current.acknowledged_at == _T2


def test_alert_cooldown_suppresses_reopen_until_window_expires(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    rule = store.put_alert_rule(
        AlertRule("cooldown", "Cooldown", "metric", "gt", 1.0, cooldown_seconds=60)
    )
    store.record_metric(MetricPoint("metric", 2.0, "count", "gauge", _T0))
    evaluate_alert(store, rule, now=_T1)
    store.record_metric(MetricPoint("metric", 0.0, "count", "gauge", _T2))
    resolved = evaluate_alert(store, rule, now=_T2)
    assert resolved.current is not None
    assert resolved.current.status == "resolved"
    store.record_metric(MetricPoint("metric", 3.0, "count", "gauge", _T2))
    suppressed = evaluate_alert(store, rule, now="2026-09-13T10:10:30.000000Z")
    assert not suppressed.changed
    assert suppressed.current == resolved.current
    reopened = evaluate_alert(store, rule, now="2026-09-13T10:12:00.000000Z")
    assert reopened.changed
    assert reopened.current is not None
    assert reopened.current.status == "open"


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
    intent = budget_notification(evaluation, now=_T2)
    assert intent is not None
    assert intent.kind == "budget"
    assert intent.attributes == (("action", "notify"), ("budget_id", "daily"))
    assert budget_gate(evaluation)


def test_persisted_metrics_can_feed_prometheus_export(tmp_path: Path) -> None:
    from studio_observability import prometheus_text

    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    store.record_metric(MetricPoint("jobs.completed", 3.0, "count", "counter", _T0, ()))
    assert prometheus_text(store.list_metrics()) == "jobs_completed 3.0\n"


def test_budget_gate_denies_only_explicit_hard_budget_action() -> None:
    from studio_finops import BudgetEvaluation

    exceeded = BudgetEvaluation(
        "b", Decimal("2"), Decimal("0"), Decimal("2"), Decimal("1"), True, "deny_new_work"
    )
    notify = BudgetEvaluation(
        "b", Decimal("2"), Decimal("0"), Decimal("2"), Decimal("1"), True, "notify"
    )
    assert not budget_gate(exceeded)
    assert budget_gate(notify)


def test_forecast_requires_alphabetic_three_letter_currency() -> None:
    forecast = forecast_cost(
        source_ref="usage-window",
        currency="eur",
        observed_cost=Decimal("4"),
        elapsed_fraction=Decimal("0.5"),
    )
    assert forecast.currency == "EUR"
    assert forecast.projected_cost == Decimal("8")
    with pytest.raises(ValueError, match="three-letter"):
        forecast_cost(
            source_ref="usage-window",
            currency="123",
            observed_cost=Decimal("4"),
            elapsed_fraction=Decimal("0.5"),
        )


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


def test_alert_cooldown_rejects_clock_rollback() -> None:
    with pytest.raises(ValueError, match="must not precede"):
        _elapsed_seconds(_T1, _T0)


def test_alert_pending_window_transitions_to_firing(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    rule = store.put_alert_rule(
        AlertRule("pending", "Pending", "metric", "gt", 1.0, pending_seconds=60)
    )
    store.record_metric(MetricPoint("metric", 2.0, "count", "gauge", _T0))
    pending = evaluate_alert(store, rule, now=_T1)
    assert pending.current is not None
    assert pending.current.status == "pending"
    firing = evaluate_alert(store, rule, now="2026-09-13T10:06:01.000000Z")
    assert firing.changed
    assert firing.current is not None
    assert firing.current.status == "firing"
    assert store.list_alert_rules()[0].pending_seconds == 60


def test_alert_http_adapter_lists_and_evaluates_rules(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    store.put_alert_rule(AlertRule("r1", "Queue", "queue", "gt", 2.0))
    store.record_metric(MetricPoint("queue", 3.0, "items", "gauge", _T0))
    adapter = AlertHTTPAdapter(store)
    assert adapter.list_rules()["items"][0]["id"] == "r1"
    result = adapter.evaluate({"rule_id": "r1"}, now=_T1)
    assert result["changed"] is True
    assert result["state"]["status"] == "open"


def test_alert_http_adapter_acknowledges_active_instance(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    rule = store.put_alert_rule(AlertRule("ack-http", "Ack", "metric", "gt", 1.0))
    store.record_metric(MetricPoint("metric", 2.0, "count", "gauge", _T0))
    current = evaluate_alert(store, rule, now=_T1).current
    assert current is not None
    result = AlertHTTPAdapter(store).acknowledge(
        {"rule_id": rule.id, "fingerprint": current.fingerprint}, now=_T2
    )
    assert result["state"]["acknowledged_at"] == str(_T2)


def test_alert_instances_are_listed_with_a_bound(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    rule = store.put_alert_rule(AlertRule("inventory", "Inventory", "metric", "gt", 1.0))
    store.record_metric(MetricPoint("metric", 2.0, "count", "gauge", _T0))
    current = evaluate_alert(store, rule, now=_T1).current
    assert current is not None
    instances = store.list_alert_instances(limit=1)
    assert len(instances) == 1
    assert instances[0].fingerprint == current.fingerprint


def test_notification_failures_are_durable_and_retryable(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    from studio_observability import NotificationIntent

    intent = NotificationIntent("n-1", "alert", "Alert", "body", _T0)
    store.put_notification_intent(intent)
    retry_at = "2099-01-01T00:00:00.000000Z"
    assert store.record_notification_failure(
        intent.id, error="temporary webhook failure", retry_at=retry_at
    )
    state = store.notification_delivery_state(intent.id)
    assert state == {
        "delivered_at": None,
        "attempt_count": 1,
        "last_error": "temporary webhook failure",
        "next_attempt_at": retry_at,
    }
    assert store.list_pending_notification_intents(limit=10) == ()
