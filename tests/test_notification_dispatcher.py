from studio_observability import (
    NotificationDispatcher,
    SqliteTelemetryStore,
    scheduler_notification,
)


class Sink:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send(self, intent):
        if self.fail:
            raise RuntimeError("temporary provider failure")
        self.sent.append(intent.id)
        return intent.id


def test_dispatcher_delivers_and_retries_failed_intents(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    intent = scheduler_notification(
        workflow_run_id="run", workflow_id="wf", state="failed", now="2026-09-21T00:00:00.000000Z"
    )
    assert intent is not None
    store.put_notification_intent(intent)
    failed = NotificationDispatcher(
        store, Sink(fail=True), clock=lambda: "2026-09-21T00:01:00.000000Z"
    ).dispatch_once()
    assert (failed.attempted, failed.delivered, failed.failed) == (1, 0, 1)
    sink = Sink()
    delivered = NotificationDispatcher(
        store, sink, clock=lambda: "2026-09-21T00:02:00.000000Z"
    ).dispatch_once()
    assert (delivered.attempted, delivered.delivered) == (1, 1)
    assert sink.sent == [intent.id]


def test_dispatcher_does_not_mark_mismatched_sink_identity_delivered(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    intent = scheduler_notification(
        workflow_run_id="run", workflow_id="wf", state="failed", now="2026-09-21T00:00:00.000000Z"
    )
    assert intent is not None
    store.put_notification_intent(intent)

    class MismatchedSink:
        def send(self, _intent):
            return "different-intent"

    result = NotificationDispatcher(
        store, MismatchedSink(), clock=lambda: "2026-09-21T00:01:00.000000Z"
    ).dispatch_once()
    assert (result.attempted, result.delivered, result.failed) == (1, 0, 1)
    assert store.list_pending_notification_intents() == (intent,)


def test_dispatcher_does_not_retry_before_retry_at(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    intent = scheduler_notification(
        workflow_run_id="run", workflow_id="wf", state="failed", now="2026-09-21T00:00:00.000000Z"
    )
    assert intent is not None
    store.put_notification_intent(intent)
    store.record_notification_failure(
        intent.id,
        error="temporary provider failure",
        retry_at="2026-09-21T00:05:00.000000Z",
    )

    result = NotificationDispatcher(
        store, Sink(), clock=lambda: "2026-09-21T00:04:59.000000Z"
    ).dispatch_once()
    assert (result.attempted, result.delivered, result.failed) == (0, 0, 0)
    assert store.list_pending_notification_intents() == (intent,)


def test_dispatcher_applies_a_durable_retry_delay_after_failure(tmp_path):
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    intent = scheduler_notification(
        workflow_run_id="run",
        workflow_id="wf",
        state="failed",
        now="2026-09-21T00:00:00.000000Z",
    )
    assert intent is not None
    store.put_notification_intent(intent)
    NotificationDispatcher(
        store,
        Sink(fail=True),
        clock=lambda: "2026-09-21T00:01:00.000000Z",
        retry_delay_seconds=60,
    ).dispatch_once()
    before = NotificationDispatcher(
        store, Sink(), clock=lambda: "2026-09-21T00:01:59.000000Z"
    ).dispatch_once()
    assert before.attempted == 0
    after = NotificationDispatcher(
        store, Sink(), clock=lambda: "2026-09-21T00:02:00.000000Z"
    ).dispatch_once()
    assert after.delivered == 1
