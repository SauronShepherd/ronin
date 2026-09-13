from datetime import datetime, timezone

from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    DataContract,
    QualityRule,
    QualityRuleId,
    QualityRunId,
)
from studio_quality import blocking_failures, evaluate_contract


_REF = AssetRef(AssetId("asset-1"), AssetVersion("v1"))


def test_builtin_quality_rules_evaluate_into_immutable_run() -> None:
    contract = DataContract(
        _REF,
        "exact",
        (
            QualityRule(QualityRuleId("not-null"), "null", "id not null", blocking=True, field="id"),
            QualityRule(QualityRuleId("unique"), "unique", "id unique", field="id"),
            QualityRule(
                QualityRuleId("range"),
                "range",
                "amount range",
                field="amount",
                parameters=(("min", "0"), ("max", "100")),
            ),
            QualityRule(
                QualityRuleId("domain"),
                "domain",
                "status domain",
                field="status",
                parameters=(("allowed", "new,done"),),
            ),
            QualityRule(
                QualityRuleId("rows"),
                "row_count",
                "row count",
                parameters=(("min", "2"),),
            ),
        ),
    )
    rows = (
        {"id": 1, "amount": 10, "status": "new"},
        {"id": 2, "amount": 20, "status": "done"},
    )
    run = evaluate_contract(contract, rows, run_id=QualityRunId("quality-1"))
    assert run.status == "passed"
    assert blocking_failures(contract, run) == ()


def test_blocking_failure_is_reported() -> None:
    contract = DataContract(
        _REF,
        "exact",
        (
            QualityRule(QualityRuleId("not-null"), "null", "id not null", blocking=True, field="id"),
        ),
    )
    run = evaluate_contract(
        contract,
        ({"id": None},),
        run_id=QualityRunId("quality-2"),
    )
    assert run.status == "failed"
    assert tuple(result.rule_id.value for result in blocking_failures(contract, run)) == ("not-null",)


def test_freshness_uses_contract_default() -> None:
    contract = DataContract(
        _REF,
        "exact",
        (
            QualityRule(
                QualityRuleId("fresh"),
                "freshness",
                "event freshness",
                field="event_time",
            ),
        ),
        freshness_seconds=3600,
    )
    run = evaluate_contract(
        contract,
        ({"event_time": "2026-09-13T09:30:00+00:00"},),
        run_id=QualityRunId("quality-3"),
        now=datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc),
    )
    assert run.status == "passed"


def test_custom_execution_kinds_fail_explicitly_not_silently() -> None:
    contract = DataContract(
        _REF,
        "exact",
        (
            QualityRule(QualityRuleId("sql"), "custom_sql", "custom SQL"),
        ),
    )
    run = evaluate_contract(contract, (), run_id=QualityRunId("quality-4"))
    assert run.status == "error"
    assert run.results[0].message == "custom_sql execution is not enabled in the built-in evaluator"
