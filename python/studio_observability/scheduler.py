"""Scheduler outcome integration for the platform notification system."""

from typing import Protocol

from studio_orchestrator import Instant

from .notifications import scheduler_notification
from .store import SqliteTelemetryStore


class SchedulerNotificationStore(Protocol):
    """Minimal durable port accepted by the scheduler notification bridge."""

    def put_notification_intent(self, intent: object) -> object: ...

    def enqueue(self, intent: object) -> bool: ...


def persist_terminal_notification(
    store: SchedulerNotificationStore | SqliteTelemetryStore,
    *,
    workflow_run_id: str,
    workflow_id: str,
    state: str,
    now: Instant | str,
    reason: str | None = None,
) -> bool:
    intent = scheduler_notification(
        workflow_run_id=workflow_run_id,
        workflow_id=workflow_id,
        state=state,
        now=now,
        reason=reason,
    )
    if intent is None:
        return False
    put = getattr(store, "put_notification_intent", None)
    if callable(put):
        put(intent)
    else:
        enqueue = getattr(store, "enqueue", None)
        if not callable(enqueue):
            raise TypeError(
                "scheduler notification store must expose put_notification_intent or enqueue"
            )
        enqueue(intent)
    return True


__all__ = ("persist_terminal_notification",)
