from studio_observability import MetricPoint
from studio_observability.prometheus import prometheus_text
from studio_orchestrator import Instant


def test_prometheus_export_is_sorted_and_escapes_labels() -> None:
    points = (
        MetricPoint("jobs.completed", 2, "count", "counter", Instant("2026-01-01T00:00:00.000000Z"), (("team", 'a"b'),)),
        MetricPoint("jobs.completed", 1, "count", "counter", Instant("2026-01-01T00:00:00.000000Z"), ()),
    )
    assert prometheus_text(points) == 'jobs_completed 1\njobs_completed{team="a\\"b"} 2\n'
