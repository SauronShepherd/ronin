from pathlib import Path

from studio_core import (
    AssetRef,
    DataContract,
    QualityRule,
    QualityRuleId,
    QualityRunId,
    WorkspaceId,
)
from studio_observability import (
    AlertRule,
    SqliteTelemetryStore,
    evaluate_alert,
    evaluate_quality_alerts,
    record_quality_metrics,
)
from studio_quality import execute_quality


def test_quality_run_is_consumable_by_common_alert_engine(tmp_path):
    workspace = WorkspaceId("ws")
    asset = AssetRef("orders", "v1")
    quality_store = _QualityStore(
        DataContract(
            asset,
            "backward",
            (QualityRule(QualityRuleId("rule-1"), "null", "id", blocking=True, field="id"),),
        )
    )
    run = execute_quality(
        quality_store,
        workspace,
        asset,
        [{"id": None}],
        run_id=QualityRunId("run-1"),
        now="2026-01-01T00:00:00Z",
    )
    telemetry = SqliteTelemetryStore(Path(tmp_path / "obs.sqlite"))
    record_quality_metrics(run, telemetry.record_metric, observed_at="2026-01-01T00:00:00.000000Z")
    transition = evaluate_alert(
        telemetry,
        AlertRule("quality", "quality failures", "quality.run.failure", "gte", 1.0),
        now="2026-01-01T00:00:00.000000Z",
    )
    assert transition.changed is True
    assert transition.current is not None
    assert transition.current.status == "open"


def test_quality_alert_adapter_returns_matching_transition_and_resolves(tmp_path):
    workspace = WorkspaceId("ws")
    asset = AssetRef("orders", "v1")
    quality_store = _QualityStore(
        DataContract(
            asset,
            "backward",
            (QualityRule(QualityRuleId("rule-1"), "null", "id", blocking=True, field="id"),),
        )
    )
    telemetry = SqliteTelemetryStore(Path(tmp_path / "obs.sqlite"))
    rule = AlertRule("quality", "quality failures", "quality.run.failure", "gte", 1.0)
    failed = execute_quality(
        quality_store,
        workspace,
        asset,
        [{"id": None}],
        run_id=QualityRunId("run-failed"),
        now="2026-01-01T00:00:00Z",
    )
    opened = evaluate_quality_alerts(
        failed,
        telemetry,
        (rule,),
        observed_at="2026-01-01T00:00:00.000000Z",
    )
    assert len(opened) == 1
    assert opened[0].changed

    passed = execute_quality(
        quality_store,
        workspace,
        asset,
        [{"id": 1}],
        run_id=QualityRunId("run-passed"),
        now="2026-01-01T00:01:00Z",
    )
    resolved = evaluate_quality_alerts(
        passed,
        telemetry,
        (rule,),
        observed_at="2026-01-01T00:01:00.000000Z",
    )
    assert len(resolved) == 1
    assert resolved[0].changed
    assert resolved[0].current is not None
    assert resolved[0].current.status == "resolved"


class _QualityStore:
    def __init__(self, contract):
        self.contract = contract
        self.runs = []

    def get_contract(self, _workspace_id, ref):
        return self.contract if ref == self.contract.asset else None

    def record_run(self, _workspace_id, run, *, now):
        _ = now
        self.runs.append(run)
        return run

    def list_runs(self, _workspace_id, _ref):
        return tuple(self.runs)
