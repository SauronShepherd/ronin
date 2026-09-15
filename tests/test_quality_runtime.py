from datetime import UTC, datetime

from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    DataContract,
    QualityRule,
    QualityRuleId,
    QualityRunId,
    WorkspaceId,
)
from studio_quality import blocking_failures, evaluate_contract, list_quality_runs

_REF = AssetRef(AssetId("asset-1"), AssetVersion("v1"))


def test_builtin_quality_rules_evaluate_into_immutable_run() -> None:
    contract = DataContract(
        _REF,
        "exact",
        (
            QualityRule(
                QualityRuleId("not-null"), "null", "id not null", blocking=True, field="id"
            ),
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
        (QualityRule(QualityRuleId("not-null"), "null", "id not null", blocking=True, field="id"),),
    )
    run = evaluate_contract(
        contract,
        ({"id": None},),
        run_id=QualityRunId("quality-2"),
    )
    assert run.status == "failed"
    assert tuple(result.rule_id.value for result in blocking_failures(contract, run)) == (
        "not-null",
    )


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
        now=datetime(2026, 9, 13, 10, 0, tzinfo=UTC),
    )
    assert run.status == "passed"


def test_custom_execution_kinds_fail_explicitly_not_silently() -> None:
    contract = DataContract(
        _REF,
        "exact",
        (QualityRule(QualityRuleId("sql"), "custom_sql", "custom SQL"),),
    )
    run = evaluate_contract(contract, (), run_id=QualityRunId("quality-4"))
    assert run.status == "error"
    assert run.results[0].message == "custom_sql execution is not enabled in the built-in evaluator"


def test_quality_history_is_exposed_through_service_boundary() -> None:
    run = evaluate_contract(
        DataContract(_REF, "exact", (QualityRule(QualityRuleId("rows"), "row_count", "rows"),)),
        ({"id": 1},),
        run_id=QualityRunId("quality-history-1"),
    )

    class Store:
        def list_runs(self, workspace_id: WorkspaceId, ref: AssetRef):
            assert workspace_id == WorkspaceId("workspace-1")
            assert ref == _REF
            return (run,)

    assert list_quality_runs(Store(), WorkspaceId("workspace-1"), _REF) == (run,)


def test_referential_rule_uses_injected_reference_values() -> None:
    from studio_core import AssetId, AssetRef, AssetVersion, DataContract, QualityRule
    from studio_quality.evaluator import evaluate_rule

    rule = QualityRule(
        QualityRuleId("fk"), "referential", "customer reference", blocking=True, field="customer_id"
    )
    contract = DataContract(AssetRef(AssetId("orders"), AssetVersion("1")), "exact", rules=(rule,))
    result = evaluate_rule(
        rule,
        [{"customer_id": "ok"}, {"customer_id": "bad"}],
        contract=contract,
        reference_values=lambda _rule: ("ok",),
    )
    assert result.status == "failed"
    assert result.observed == (("reference_count", "1"), ("violation_count", "1"))


def test_custom_sql_rule_uses_injected_sandboxed_predicate() -> None:
    from studio_core import QualityRule
    from studio_quality.evaluator import evaluate_rule

    rule = QualityRule(QualityRuleId("sql"), "custom_sql", "row predicate", field=None)
    contract = DataContract(_REF, "exact", rules=(rule,))
    result = evaluate_rule(
        rule, [{"id": 1}], contract=contract, custom_sql=lambda _rule, rows: len(rows) == 1
    )
    assert result.status == "passed"


def test_custom_python_rule_uses_injected_sandboxed_predicate() -> None:
    from studio_quality.evaluator import evaluate_rule

    rule = QualityRule(QualityRuleId("python"), "custom_python", "row predicate")
    contract = DataContract(_REF, "exact", rules=(rule,))
    result = evaluate_rule(
        rule, [{"id": 1}], contract=contract, custom_python=lambda _rule, rows: rows[0]["id"] == 1
    )
    assert result.status == "passed"
