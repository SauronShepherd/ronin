from __future__ import annotations

from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    QualityResult,
    QualityRuleId,
    QualityRun,
    QualityRunId,
)
from studio_quality import quality_alert_signals


def test_quality_alert_signals_project_rule_and_run_state() -> None:
    run = QualityRun(
        QualityRunId("run-1"),
        AssetRef(AssetId("asset-1"), AssetVersion("v1")),
        "execution-1",
        (
            QualityResult(QualityRuleId("rule-failed"), "failed"),
            QualityResult(QualityRuleId("rule-ok"), "passed"),
        ),
    )
    signals = quality_alert_signals(run)
    assert [signal.metric_name for signal in signals] == [
        "quality.rule.failure",
        "quality.rule.failure",
        "quality.run.failure",
    ]
    assert [signal.value for signal in signals] == [1.0, 0.0, 1.0]
    assert signals[0].attributes[1] == ("rule_id", "rule-failed")
