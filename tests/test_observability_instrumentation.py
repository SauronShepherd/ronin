import pytest
from studio_observability import MetricPoint, TelemetryEvent, instrument_execution
from studio_orchestrator import Instant


def test_instrumentation_records_success_and_failure() -> None:
    metrics: list[MetricPoint] = []
    events: list[TelemetryEvent] = []
    now = Instant("2026-09-15T00:00:00.000000Z")
    assert (
        instrument_execution(
            "job",
            lambda: 7,
            record_metric=metrics.append,
            record_event=events.append,
            observed_at=now,
        )
        == 7
    )
    assert metrics[0].name == "execution.job.duration_ms"
    with pytest.raises(RuntimeError):
        instrument_execution(
            "job",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            record_metric=metrics.append,
            record_event=events.append,
            observed_at=now,
        )
    assert events[0].name == "execution.job.failed"
