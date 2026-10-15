from pathlib import Path

from studio_observability import (
    NotificationDispatcher,
    SqliteNotificationIntentStore,
    SqliteTelemetryStore,
    persist_terminal_notification,
    scheduler_notification,
)


def test_sqlite_notification_store_is_idempotent_and_dispatchable(tmp_path: Path) -> None:
    store = SqliteNotificationIntentStore(tmp_path / "notifications.db")
    intent = scheduler_notification(
        workflow_run_id="run-store",
        workflow_id="wf-1",
        state="failed",
        now="2026-09-21T00:00:00.000000Z",
    )
    assert intent is not None
    assert store.enqueue(intent) is True
    assert store.enqueue(intent) is False
    sent: list[str] = []
    result = NotificationDispatcher(
        store,
        type("Sink", (), {"send": lambda _self, value: sent.append(value.id) or value.id})(),
        clock=lambda: "2026-09-21T00:00:01.000000Z",
    ).dispatch_once()
    assert result.delivered == 1
    assert sent == [intent.id]
    assert store.list_pending_notification_intents() == ()


def test_scheduler_notification_is_terminal_and_idempotent() -> None:
    now = "2026-09-21T00:00:00.000000Z"
    assert (
        scheduler_notification(
            workflow_run_id="run-1", workflow_id="wf-1", state="running", now=now
        )
        is None
    )
    first = scheduler_notification(
        workflow_run_id="run-1",
        workflow_id="wf-1",
        state="failed",
        now=now,
        reason="operator-visible failure",
    )
    second = scheduler_notification(
        workflow_run_id="run-1",
        workflow_id="wf-1",
        state="failed",
        now=now,
        reason="operator-visible failure",
    )
    assert first == second


def test_notification_intents_are_durable_and_claimed_once(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    intent = scheduler_notification(
        workflow_run_id="run-1",
        workflow_id="wf-1",
        state="succeeded",
        now="2026-09-21T00:00:00.000000Z",
    )
    assert intent is not None
    store.put_notification_intent(intent)
    store.put_notification_intent(intent)
    assert store.list_pending_notification_intents() == (intent,)
    assert store.mark_notification_delivered(intent.id, delivered_at="2026-09-21T00:01:00.000000Z")
    assert not store.mark_notification_delivered(
        intent.id, delivered_at="2026-09-21T00:02:00.000000Z"
    )
    assert store.list_pending_notification_intents() == ()


def test_persist_terminal_notification_is_idempotent(tmp_path: Path) -> None:
    store = SqliteTelemetryStore(tmp_path / "telemetry.sqlite")
    kwargs = {
        "workflow_run_id": "run-2",
        "workflow_id": "wf-2",
        "state": "cancelled",
        "now": "2026-09-21T00:00:00.000000Z",
    }
    assert persist_terminal_notification(store, **kwargs)
    assert persist_terminal_notification(store, **kwargs)
    assert len(store.list_pending_notification_intents()) == 1


def test_persist_terminal_notification_feeds_dispatcher_store(tmp_path: Path) -> None:
    store = SqliteNotificationIntentStore(tmp_path / "notifications.sqlite")
    kwargs = {
        "workflow_run_id": "run-dispatch",
        "workflow_id": "wf-dispatch",
        "state": "failed",
        "now": "2026-09-21T00:00:00.000000Z",
    }
    assert persist_terminal_notification(store, **kwargs)
    sent: list[str] = []
    result = NotificationDispatcher(
        store,
        type("Sink", (), {"send": lambda _self, value: sent.append(value.id) or value.id})(),
        clock=lambda: "2026-09-21T00:00:01.000000Z",
    ).dispatch_once()
    assert result.delivered == 1
    assert sent == ["scheduler:run-dispatch:failed"]
